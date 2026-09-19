#!/usr/bin/env python3
"""
Build papers.json from live data.

Two sources, because neither one has everything:

  OpenAlex  — which works are retracted, and citations per year.
              Free, no key, no signup.
  Crossref  — WHEN each one was retracted. OpenAlex has is_retracted
              (a boolean) but no retraction date, so the date comes from
              Retraction Watch, which Crossref publishes on the original
              work's record under "updated-by".

Standard library only. Run it:

    python3 fetch_papers.py
    python3 fetch_papers.py --target 400 --min-citations 80

THE ONE THING THAT MATTERS FOR HONESTY
--------------------------------------
OpenAlex's counts_by_year is a rolling window of roughly the last 15
years. Ask it about a paper from 1998 and you get citations from 2012
onwards and nothing before, so most of that paper's BEFORE-retraction
life is simply missing from the breakdown while its AFTER life is
complete. Using those papers would inflate the posthumous share — an
error pointing in exactly the direction of our own argument.

So this script keeps only papers whose entire citation history fits
inside the window, and then checks each one: the per-year counts must
add up to the headline cited_by_count. Anything that does not reconcile
is dropped and reported. That is why the output starts around 2012
rather than 1995.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Both APIs run a faster, more reliable "polite pool" for requests that
# identify themselves. Put an email address here to use it. Left empty,
# the script still works, just on the shared anonymous pool.
MAILTO = ""

# An OpenAlex API key. FREE, no payment, takes a minute:
#   https://help.openalex.org/api/authentication/
#
# Without one every request counts against a daily budget shared by
# EVERYONE on your IP, which is how we exhausted it: the response says
# "$0 remaining; resets at midnight UTC". With a key you get your own
# budget and none of this recurs. Can also be supplied as OPENALEX_KEY
# in the environment so the key never lands in the repo.
API_KEY = os.environ.get("OPENALEX_KEY", "")

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
THIS_YEAR = datetime.date.today().year

USER_AGENT = "afterlife-hophacks/1.0" + (f" (mailto:{MAILTO})" if MAILTO else "")


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------

def get(url, params, tries=4):
    """GET some JSON, retrying on rate limits and server errors."""
    if MAILTO:
        params = {**params, "mailto": MAILTO}
    if API_KEY:
        params = {**params, "api_key": API_KEY}
    full = f"{url}?{urllib.parse.urlencode(params)}"

    for attempt in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            # 429 = too fast, 5xx = their end. Both are worth retrying.
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                # Honour Retry-After when the server sends one, rather
                # than guessing and getting throttled again.
                wait = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(wait)
                except (TypeError, ValueError):
                    wait = 2 ** attempt
                time.sleep(min(wait, 30))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("unreachable")


# ----------------------------------------------------------------------
# Step 1 — how far back does OpenAlex's yearly breakdown actually go?
# ----------------------------------------------------------------------

def detect_window_start():
    """
    Find the earliest year OpenAlex will report citations for.

    Measured rather than assumed, because it is a rolling window: it
    moves every January, and a hard-coded year would quietly start
    admitting truncated papers a few months from now.
    """
    data = get(OPENALEX, {
        "filter": "is_retracted:true",
        "sort": "cited_by_count:desc",
        "per-page": 50,
        "select": "publication_year,counts_by_year",
    })
    years = [c["year"] for w in data["results"] for c in (w.get("counts_by_year") or [])]
    if not years:
        raise SystemExit("OpenAlex returned no yearly counts at all.")
    return min(years)


# ----------------------------------------------------------------------
# Step 2 — candidate retracted works from OpenAlex
# ----------------------------------------------------------------------

def fetch_candidates(min_pub_year, min_citations, wanted):
    """
    Page through retracted works, most cited first.

    Most cited first is not cherry-picking the result: the finding is
    about how far an idea spreads after it is declared dead, so papers
    nobody cited either way carry no signal. It IS a sampling choice
    though, and one to say out loud rather than bury.
    """
    out = []
    cursor = "*"
    pages = 0

    while cursor and len(out) < wanted * 3:   # over-fetch; many will fail the checks
        data = get(OPENALEX, {
            "filter": f"is_retracted:true,publication_year:>{min_pub_year - 1},"
                      f"cited_by_count:>{min_citations - 1}",
            "sort": "cited_by_count:desc",
            "per-page": 200,
            "cursor": cursor,
            "select": "id,doi,title,publication_year,cited_by_count,counts_by_year",
        })
        results = data["results"]
        if not results:
            break

        out.extend(results)
        cursor = data["meta"].get("next_cursor")
        pages += 1
        print(f"  OpenAlex page {pages}: {len(out)} candidates", file=sys.stderr)

    return out


# ----------------------------------------------------------------------
# Step 3 — retraction dates from Crossref
# ----------------------------------------------------------------------

def bare_doi(doi_url):
    """OpenAlex stores DOIs as full URLs; Crossref wants the bare form."""
    if not doi_url:
        return None
    return doi_url.replace("https://doi.org/", "").replace("http://dx.doi.org/", "").lower()


def load_retraction_table(cache="retraction_dates.json"):
    """
    The ENTIRE Crossref retraction table, pulled once and cached.

    This is what makes scale possible. Looking each DOI up individually
    costs one request per 40 papers, so 20,000 papers is 500 requests
    every run, and Crossref starts refusing at that rate. The whole
    table is ~76 cursor pages, fetched once, after which any number of
    papers is a free dictionary lookup.

    A paper can carry more than one retraction notice (a correction
    later escalated, or the same notice indexed twice). The EARLIEST
    wins: that is the date the claim was first withdrawn.
    """
    if os.path.exists(cache):
        table = json.load(open(cache))
        print(f"   {len(table):,} retraction dates from {cache}", file=sys.stderr)
        return table

    print("   downloading the Crossref retraction table (once)...", file=sys.stderr)
    table, cursor, pages = {}, "*", 0

    while cursor:
        url = (f"{CROSSREF}?filter=update-type:retraction&rows=1000"
               f"&select=DOI,update-to&cursor={urllib.parse.quote(cursor)}")
        if MAILTO:
            url += f"&mailto={MAILTO}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    msg = json.loads(r.read().decode())["message"]
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)

        items = msg.get("items", [])
        if not items:
            break

        for it in items:
            for u in (it.get("update-to") or []):
                if u.get("type") != "retraction":
                    continue
                doi = (u.get("DOI") or "").lower()
                parts = (u.get("updated") or {}).get("date-parts") or []
                if doi and parts and parts[0] and parts[0][0]:
                    y = int(parts[0][0])
                    if doi not in table or y < table[doi]:
                        table[doi] = y

        cursor = msg.get("next-cursor")
        pages += 1
        print(f"     page {pages}: {len(table):,} dated dois", file=sys.stderr)
        time.sleep(0.2)

    json.dump(table, open(cache, "w"))
    print(f"   cached {len(table):,} retraction dates to {cache}", file=sys.stderr)
    return table


def fetch_retraction_years(dois, batch=40, workers=3):
    """
    Look up when each DOI was retracted.

    Crossref lets several dois be OR'd into one filter, so these go up in
    batches rather than one request per paper. A paper can carry more
    than one retraction notice (a correction that was later escalated, or
    the same notice indexed twice) — the EARLIEST is the one that counts,
    since that is the date the claim was first withdrawn.
    """
    batches = [dois[i:i + batch] for i in range(0, len(dois), batch)]
    found = {}

    def run(chunk):
        params = {
            "filter": ",".join(f"doi:{d}" for d in chunk),
            "select": "DOI,updated-by",
            "rows": len(chunk),
        }
        try:
            items = get(CROSSREF, params)["message"]["items"]
        except Exception as e:
            print(f"  ! crossref batch failed: {e}", file=sys.stderr)
            return {}

        time.sleep(0.4)          # stay under Crossref's rate limit
        got = {}
        for it in items:
            years = []
            for u in (it.get("updated-by") or []):
                if u.get("type") != "retraction":
                    continue
                parts = (u.get("updated") or {}).get("date-parts") or []
                if parts and parts[0] and parts[0][0]:
                    years.append(int(parts[0][0]))
            if years:
                got[it["DOI"].lower()] = min(years)
        return got

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, got in enumerate(pool.map(run, batches), 1):
            found.update(got)
            print(f"  Crossref batch {i}/{len(batches)}: {len(found)} dates", file=sys.stderr)

    return found


# ----------------------------------------------------------------------
# Step 4 — build one record, or explain why not
# ----------------------------------------------------------------------

def build_record(work, retracted_year, window_start, tolerance):
    """
    Returns (record, None) or (None, reason-it-was-rejected).

    Every rejection is counted and printed. A pipeline that silently
    drops rows is one you cannot defend.
    """
    pub = work.get("publication_year")
    title = work.get("title") or work.get("display_name")
    counts = work.get("counts_by_year") or []

    # Publishers prefix retracted articles with "RETRACTED:" in the
    # metadata. That is the publisher's label, not the paper's title,
    # and the page already says so in letters an inch high.
    if title:
        for prefix in ("RETRACTED ARTICLE:", "RETRACTED:", "Retracted:",
                       "RETRACTED ARTICLE :", "[RETRACTED]"):
            if title.upper().startswith(prefix.upper()):
                title = title[len(prefix):].strip()
                break

    if not pub or not title or not counts:
        return None, "missing basic fields"

    if pub < window_start:
        return None, "published before the counts_by_year window"

    if retracted_year < pub:
        return None, "retracted before it was published"

    if retracted_year > THIS_YEAR:
        return None, "retraction year in the future"

    # Citations dated before the publication year do happen (preprints
    # circulate, and metadata is imperfect). Fold them into the
    # publication year: they are real citations, they are unambiguously
    # in the "before" era, and leaving them at a negative age would draw
    # lines running backwards out of the publication dot.
    curve = {}
    for c in counts:
        y, n = c["year"], c["cited_by_count"]
        if n <= 0:
            continue
        curve[max(y, pub)] = curve.get(max(y, pub), 0) + n

    if not curve:
        return None, "no citations in any year"

    # THE RECONCILIATION CHECK. If the yearly breakdown does not add up
    # to the headline total, this paper's history is clipped and its
    # before/after split would be wrong.
    total = sum(curve.values())
    headline = work.get("cited_by_count") or 0
    if headline and abs(headline - total) > max(tolerance, headline * 0.02):
        return None, f"yearly counts do not reconcile (off by {headline - total})"

    # The retraction year itself counts as after. This is the rule fixed
    # in the brief before any code was written, and it lives in exactly
    # one place: here.
    before = sum(n for y, n in curve.items() if y < retracted_year)
    after = sum(n for y, n in curve.items() if y >= retracted_year)

    return {
        "id": work["id"].rsplit("/", 1)[-1],
        "title": title,
        "published_year": pub,
        "retracted_year": retracted_year,
        "citations_by_year": {str(y): curve[y] for y in sorted(curve)},
        "citations_before": before,
        "citations_after": after,
    }, None


# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=300,
                    help="how many papers to keep; 0 keeps everything")
    ap.add_argument("--min-citations", type=int, default=40,
                    help="skip papers cited fewer times than this (default 40)")
    ap.add_argument("--tolerance", type=int, default=5,
                    help="citations the yearly counts may be off by (default 5)")
    ap.add_argument("--out", default="papers.json")
    args = ap.parse_args()

    if not MAILTO:
        print("note: MAILTO is empty. Set it at the top of this file for the\n"
              "      faster 'polite pool' on both APIs.\n", file=sys.stderr)

    print("1. measuring OpenAlex's yearly-count window...", file=sys.stderr)
    window_start = detect_window_start()
    print(f"   window starts {window_start}; only papers published "
          f"{window_start} or later can be trusted\n", file=sys.stderr)

    print("2. fetching retracted works...", file=sys.stderr)
    works = fetch_candidates(window_start, args.min_citations, args.target)
    print(f"   {len(works)} candidates\n", file=sys.stderr)

    by_doi = {}
    for w in works:
        d = bare_doi(w.get("doi"))
        if d:
            by_doi[d] = w
    print(f"3. retraction dates for {len(by_doi):,} dois...", file=sys.stderr)
    years = load_retraction_table()
    hits = sum(1 for d in by_doi if d in years)
    print(f"   {hits:,} of them are in the table\n", file=sys.stderr)

    print("4. building records...", file=sys.stderr)
    papers, rejected = [], {}
    for doi, w in by_doi.items():
        if doi not in years:
            rejected["no retraction date in Crossref"] = \
                rejected.get("no retraction date in Crossref", 0) + 1
            continue
        rec, why = build_record(w, years[doi], window_start, args.tolerance)
        if rec:
            papers.append(rec)
        else:
            rejected[why] = rejected.get(why, 0) + 1

    # ORDER MATTERS, and getting it wrong is a real trap. Papers arrive
    # from OpenAlex most-cited first, so truncating to --target here
    # takes the most-cited ones. Truncating AFTER a chronological sort
    # would instead take the earliest-retracted ones, and papers
    # retracted early in their life are exactly the papers with the
    # highest posthumous share — which would manufacture the result
    # this project is trying to measure.
    papers = papers[:args.target] if args.target else papers

    # Only now sort for the file, so the field view reads as an archive
    # rather than a ranking.
    papers.sort(key=lambda p: (p["retracted_year"], p["published_year"]))

    with open(args.out, "w") as f:
        json.dump(papers, f, indent=1)
        f.write("\n")

    # ---- the summary you can quote at a judge ----
    print("\n   dropped:", file=sys.stderr)
    for why, n in sorted(rejected.items(), key=lambda kv: -kv[1]):
        print(f"     {n:>5}  {why}", file=sys.stderr)

    if not papers:
        print("\nNo papers survived. Try --min-citations lower.", file=sys.stderr)
        return

    tot_before = sum(p["citations_before"] for p in papers)
    tot_after = sum(p["citations_after"] for p in papers)
    tot = tot_before + tot_after
    posthumous = [p["citations_after"] / (p["citations_before"] + p["citations_after"])
                  for p in papers if (p["citations_before"] + p["citations_after"])]
    posthumous.sort()
    median = posthumous[len(posthumous) // 2]

    pub_lo = min(p["published_year"] for p in papers)
    cite_hi = max(int(y) for p in papers for y in p["citations_by_year"])

    # The posthumous share depends enormously on how quickly a paper was
    # retracted and how long ago that was, so those are reported next to
    # it. Without them the headline number invites a question you cannot
    # answer.
    lags = sorted(p["retracted_year"] - p["published_year"] for p in papers)
    med_lag = lags[len(lags) // 2]
    since = sorted(cite_hi - p["retracted_year"] for p in papers)
    med_since = since[len(since) // 2]

    print(f"\n   wrote {len(papers)} papers to {args.out}", file=sys.stderr)
    print(f"   citations before retraction : {tot_before:>9,}", file=sys.stderr)
    print(f"   citations after  retraction : {tot_after:>9,}  "
          f"({tot_after / tot:.0%} of all citations)", file=sys.stderr)
    print(f"   median paper's posthumous share: {median:.0%}", file=sys.stderr)
    print(f"   median years published -> retracted: {med_lag}", file=sys.stderr)
    print(f"   median years retracted -> now      : {med_since}", file=sys.stderr)
    print(f"   retraction lag quartiles: {lags[len(lags)//4]} / {med_lag} / "
          f"{lags[3*len(lags)//4]} years", file=sys.stderr)

    # The share above is not a like-for-like comparison: the median
    # paper here spent 2 years alive and 4 years retracted, so it had
    # more years in which to collect posthumous citations. This is the
    # comparison that controls for that — citations per year in each
    # era. It is the number to quote if anyone pushes back, and it is
    # the weaker, more honest one.
    rates = []
    for p in papers:
        alive = p["retracted_year"] - p["published_year"]
        dead = max(int(y) for y in p["citations_by_year"]) - p["retracted_year"] + 1
        if alive >= 1 and dead >= 1:
            rates.append((p["citations_before"] / alive, p["citations_after"] / dead))
    if rates:
        ratios = sorted(a / b for b, a in ((x, y) for x, y in rates) if b > 0)
        mb = sorted(r[0] for r in rates)[len(rates) // 2]
        ma = sorted(r[1] for r in rates)[len(rates) // 2]
        print(f"\n   PER YEAR, which controls for the time asymmetry:", file=sys.stderr)
        print(f"     median citations/year while valid    : {mb:.1f}", file=sys.stderr)
        print(f"     median citations/year after retraction: {ma:.1f}", file=sys.stderr)
        print(f"     median per-paper ratio after/before   : "
              f"{ratios[len(ratios)//2]:.2f}x", file=sys.stderr)
        print(f"     papers cited MORE per year after than before: "
              f"{sum(1 for b, a in rates if a > b)}/{len(rates)}", file=sys.stderr)
    print(f"\n   set these in index.html:", file=sys.stderr)
    print(f"     YEAR_MIN = {pub_lo}", file=sys.stderr)
    print(f"     YEAR_MAX = {cite_hi + 1}", file=sys.stderr)


if __name__ == "__main__":
    main()
