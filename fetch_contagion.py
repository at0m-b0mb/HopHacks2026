#!/usr/bin/env python3
"""
Second-degree citation contagion for retracted papers.

THE GAP THIS FILLS
------------------
Everything published on retracted-paper citation counts the FIRST ring:
works that cite the retracted paper directly. Those authors at least had
the retracted paper in their hands.

The second ring is works that cite a work that cited it. Those authors
very likely have no idea a retraction sits anywhere in their reference
chain. That is the claim SPREADING rather than merely persisting, and it
is the thing nobody appears to have measured.

WHAT IT COMPUTES, PER RETRACTED PAPER
-------------------------------------
    ring 1   distinct works citing the paper
    ring 2   distinct works citing a ring-1 work,
             excluding the paper itself and everything already in ring 1

both as year histograms, so each ring can be split on the retraction
date the same way the single-paper view already splits direct citations.

Ring 2 is deduplicated properly, as a set of work ids, rather than by
summing per-batch counts. Summing would count a work once for every
ring-1 paper it happens to cite, which inflates the headline by a large
and unknown factor. A work that inherits the claim by three routes is
still one work that inherited the claim.

    python3 fetch_contagion.py W2144590229
    python3 fetch_contagion.py --sample 25 --max-ring1 200

Standard library only. Results cache to contagion/<id>.json, so a second
run of the same paper is instant.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# See fetch_papers.py — both APIs run a faster pool for requests that
# identify themselves. Put an email here to use it.
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
CACHE_DIR = "contagion"

# OpenAlex accepts up to 100 ids OR'd into one filter. 200 returns a 400,
# so this is a hard ceiling rather than a tuning knob.
OR_LIMIT = 100

USER_AGENT = "afterlife-hophacks/1.0" + (f" (mailto:{MAILTO})" if MAILTO else "")


def get(params, tries=5):
    if MAILTO:
        params = {**params, "mailto": MAILTO}
    if API_KEY:
        params = {**params, "api_key": API_KEY}
    url = f"{OPENALEX}?{urllib.parse.urlencode(params, safe='|:><')}"

    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(min(2 ** attempt, 20))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(min(2 ** attempt, 20))
                continue
            raise
    raise RuntimeError("unreachable")


def short(work_id):
    return work_id.rsplit("/", 1)[-1]


def cited_by(filter_value, want_years=True):
    """
    Every work citing filter_value (one id, or several OR'd with |).

    Returns {work_id: publication_year}. Paged with a cursor rather than
    page numbers: OpenAlex caps page-number paging at 10,000 records,
    and these result sets run far past that.
    """
    out = {}
    cursor = "*"
    select = "id,publication_year" if want_years else "id"

    while cursor:
        d = get({
            "filter": f"cites:{filter_value}",
            "per-page": 200,
            "cursor": cursor,
            "select": select,
        })
        for w in d["results"]:
            out[short(w["id"])] = w.get("publication_year")
        if not d["results"]:
            break
        cursor = d["meta"].get("next_cursor")

    return out


def count_only(filter_value):
    """Just how many, without pulling the records."""
    return get({"filter": f"cites:{filter_value}", "per-page": 1})["meta"]["count"]


def histogram(year_map):
    h = {}
    for y in year_map.values():
        if y:
            h[str(y)] = h.get(str(y), 0) + 1
    return dict(sorted(h.items()))


def contagion(paper_id, max_ring1=None, workers=6, verbose=True):
    cache = os.path.join(CACHE_DIR, f"{paper_id}.json")
    if os.path.exists(cache):
        if verbose:
            print(f"  {paper_id}: cached", file=sys.stderr)
        return json.load(open(cache))

    # ---- ring 1 -----------------------------------------------------
    ring1 = cited_by(paper_id)
    ring1_ids = sorted(ring1)
    if verbose:
        print(f"  {paper_id}: ring 1 = {len(ring1_ids):,}", file=sys.stderr)

    sampled = False
    if max_ring1 and len(ring1_ids) > max_ring1:
        # Evenly spaced rather than the first N, which would be biased by
        # whatever order OpenAlex returns.
        step = len(ring1_ids) / max_ring1
        ring1_ids = [ring1_ids[int(i * step)] for i in range(max_ring1)]
        sampled = True
        if verbose:
            print(f"    sampling {max_ring1} of them", file=sys.stderr)

    # ---- ring 2 -----------------------------------------------------
    batches = [ring1_ids[i:i + OR_LIMIT] for i in range(0, len(ring1_ids), OR_LIMIT)]

    ring2 = {}

    def run(batch):
        return cited_by("|".join(batch))

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(run, batches):
            ring2.update(got)          # dict update IS the deduplication
            done += 1
            if verbose:
                print(f"    ring 2 batch {done}/{len(batches)}: "
                      f"{len(ring2):,} distinct so far", file=sys.stderr)

    # A work already in ring 1, or the retracted paper itself, is not a
    # second-degree inheritor. Remove both before reporting.
    for wid in list(ring1) + [paper_id]:
        ring2.pop(wid, None)

    result = {
        "id": paper_id,
        "ring1_count": len(ring1),
        "ring2_count": len(ring2),
        "ring1_by_year": histogram(ring1),
        "ring2_by_year": histogram(ring2),
        "ring1_sampled_to": len(ring1_ids) if sampled else None,
    }

    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(result, open(cache, "w"), indent=1)
    return result


def split(hist, retracted_year):
    """Retraction year counts as after — the same rule as everywhere else."""
    before = sum(n for y, n in hist.items() if int(y) < retracted_year)
    after = sum(n for y, n in hist.items() if int(y) >= retracted_year)
    return before, after


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="OpenAlex work ids, e.g. W2144590229")
    ap.add_argument("--papers", default="papers.json")
    ap.add_argument("--sample", type=int,
                    help="instead of ids, take N papers spread across papers.json")
    ap.add_argument("--max-ring1", type=int,
                    help="cap ring-1 papers expanded (speed vs completeness)")
    ap.add_argument("--out", default="contagion.json")
    args = ap.parse_args()

    papers = {p["id"]: p for p in json.load(open(args.papers))}

    if args.sample:
        keys = sorted(papers)
        step = len(keys) / args.sample
        targets = [keys[int(i * step)] for i in range(args.sample)]
    else:
        targets = args.ids or [next(iter(papers))]

    print(f"measuring {len(targets)} paper(s)\n", file=sys.stderr)

    rows = []
    for pid in targets:
        paper = papers.get(pid)
        if not paper:
            print(f"  {pid}: not in {args.papers}, skipping", file=sys.stderr)
            continue
        try:
            c = contagion(pid, max_ring1=args.max_ring1)
        except Exception as e:
            print(f"  {pid}: FAILED {e}", file=sys.stderr)
            continue

        r = paper["retracted_year"]
        b1, a1 = split(c["ring1_by_year"], r)
        b2, a2 = split(c["ring2_by_year"], r)

        rows.append({**c,
                     "title": paper["title"],
                     "retracted_year": r,
                     "ring1_before": b1, "ring1_after": a1,
                     "ring2_before": b2, "ring2_after": a2})

        print(f"    ring1 {c['ring1_count']:>7,} ({a1:,} after)   "
              f"ring2 {c['ring2_count']:>8,} ({a2:,} after)   "
              f"amplification x{c['ring2_count']/max(1,c['ring1_count']):.0f}\n",
              file=sys.stderr)

    json.dump(rows, open(args.out, "w"), indent=1)

    if not rows:
        return

    t1 = sum(r["ring1_count"] for r in rows)
    t2 = sum(r["ring2_count"] for r in rows)
    a1 = sum(r["ring1_after"] for r in rows)
    a2 = sum(r["ring2_after"] for r in rows)

    print(f"\n  wrote {args.out}", file=sys.stderr)
    print(f"  ring 1 total {t1:>10,}   after retraction {a1:>10,}", file=sys.stderr)
    print(f"  ring 2 total {t2:>10,}   after retraction {a2:>10,}", file=sys.stderr)
    print(f"  the indirect ring is {t2/max(1,t1):.0f}x the direct one",
          file=sys.stderr)
    print(f"\n  NOTE: ring-2 totals are summed across papers, so a work "
          f"inheriting\n  from two different retracted papers is counted "
          f"in both. Per paper\n  it is deduplicated exactly.", file=sys.stderr)


if __name__ == "__main__":
    main()
