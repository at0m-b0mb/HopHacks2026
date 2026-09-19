#!/usr/bin/env python3
"""
The transmission tree for one retracted paper, two generations deep.

    generation 1   works that cite the retracted paper
    generation 2   works that cite one of those

fetch_contagion.py answers "how many" by deduplicating ring 2 into a
set. This answers "through what route", which is what you need in order
to DRAW it: every generation-1 paper carries its own citation history,
and that history is the branch growing out of it.

The trick that makes this cheap: a direct citer's own cited_by_count is
exactly its branching factor, and it comes back in the same request
that lists the citers. One pass over ~10 pages, no second crawl.

    python3 fetch_tree.py W2144590229

COUNTING, SAID PRECISELY
------------------------
Summing the children's citation counts counts a work once per branch it
arrives on. A paper citing three different generation-1 works inherits
the claim by three routes and is counted three times here. That number
is TRANSMISSION PATHS, and it is the honest label for what gets drawn,
because each path is a separate act of passing the claim along.

The deduplicated count of distinct works — the one to quote as a
headline — comes from fetch_contagion.py. The two are different
questions and the gap between them is large, so they are never mixed.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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
USER_AGENT = "afterlife-hophacks/1.0" + (f" (mailto:{MAILTO})" if MAILTO else "")


CACHE_DIR = "tree_cache"


def get(params, tries=7):
    """
    One request, cached on disk by its parameters.

    Without this a rate-limit part way through throws away every page
    already fetched, and the next attempt starts from zero and hits the
    same limit again. With it, a re-run replays what is already on disk
    instantly and only asks the API for what is genuinely missing, so
    repeated 429s converge instead of looping forever.
    """
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)

    if MAILTO:
        params = {**params, "mailto": MAILTO}
    if API_KEY:
        params = {**params, "api_key": API_KEY}
    url = f"{OPENALEX}?{urllib.parse.urlencode(params, safe='|:><')}"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(path, "w") as fh:
                json.dump(data, fh)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                # 429 means we have been going too hard; wait properly.
                time.sleep(min(5 * (attempt + 1), 45))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(min(2 ** attempt, 20))
                continue
            raise
    raise RuntimeError("unreachable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", help="OpenAlex work id, e.g. W2144590229")
    ap.add_argument("--papers", default="papers.json")
    ap.add_argument("--out")
    ap.add_argument("--pace", type=float, default=0.6,
                    help="seconds between pages, to stay under the rate limit")
    args = ap.parse_args()

    papers = {p["id"]: p for p in json.load(open(args.papers))}
    paper = papers.get(args.id)
    if not paper:
        raise SystemExit(f"{args.id} is not in {args.papers}")

    children = []
    cursor, page = "*", 0

    while cursor:
        d = get({
            "filter": f"cites:{args.id}",
            "per-page": 200,
            "cursor": cursor,
            # publication_year places the branch on the timeline;
            # counts_by_year is the branch itself.
            "select": "id,publication_year,cited_by_count,counts_by_year",
        })
        if not d["results"]:
            break

        for w in d["results"]:
            y = w.get("publication_year")
            if not y:
                continue
            by = {str(c["year"]): c["cited_by_count"]
                  for c in (w.get("counts_by_year") or [])
                  if c["cited_by_count"] > 0}
            children.append({
                "y": y,
                "n": w.get("cited_by_count") or 0,
                "by": by,
            })

        cursor = d["meta"].get("next_cursor")
        page += 1
        print(f"  page {page}: {len(children):,} direct citers", file=sys.stderr)
        time.sleep(args.pace)

    # Chronological, so the renderer can reveal generation 1 in the same
    # order the single-paper fan already uses.
    children.sort(key=lambda c: c["y"])

    r = paper["retracted_year"]
    g1_after = sum(1 for c in children if c["y"] >= r)
    paths = sum(c["n"] for c in children)
    paths_after = sum(n for c in children for y, n in c["by"].items() if int(y) >= r)

    out = {
        "id": args.id,
        "title": paper["title"],
        "published_year": paper["published_year"],
        "retracted_year": r,
        "gen1_count": len(children),
        "gen1_after": g1_after,
        "gen2_paths": paths,
        "gen2_paths_after": paths_after,
        "children": children,
    }

    path = args.out or f"tree_{args.id}.json"
    json.dump(out, open(path, "w"))

    print(f"\n  wrote {path}", file=sys.stderr)
    print(f"  generation 1 : {len(children):>9,}  ({g1_after:,} after retraction)",
          file=sys.stderr)
    print(f"  generation 2 : {paths:>9,}  ({paths_after:,} after retraction)",
          file=sys.stderr)
    print(f"  branching    : {paths/max(1,len(children)):.1f} onward citations "
          f"per direct citer", file=sys.stderr)
    print(f"\n  these are transmission PATHS, not distinct works — see the "
          f"module docstring", file=sys.stderr)


if __name__ == "__main__":
    main()
