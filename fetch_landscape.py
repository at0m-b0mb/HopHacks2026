#!/usr/bin/env python3
"""
Where retracted papers SIT on the map of biomedical research.

Source: the Nomic PubMed landscape, 20,672,357 papers embedded in 2D by
text similarity. https://static.nomic.ai/pubmed.html

This asks a different question from the rest of the project. The
timeline asks WHEN citations arrive relative to the retraction. This
asks WHERE in the literature retractions happen at all — whether being
retracted is a property of a paper, or partly a property of the
neighbourhood the paper sits in.

HOW THE DATA IS SHAPED
----------------------
The map is served as a deepscatter quadtree. Every tile is a gzipped
Arrow file at {z}/{x}/{y}.feather holding ~1000 papers with x, y, year
and title, and each tile has SIDECAR files beside it at
{z}/{x}/{y}.<name>.feather, aligned row for row. The two that matter
here are `retracted` and `citation_count`.

The quadtree is built so that shallow tiles hold a spread of points
from across the whole map rather than one corner of it. That makes
depth-limited crawling a uniform random sample of all 20.7M papers,
which is what makes this tractable in an afternoon: at depth 5 it is
roughly 1,300 tiles instead of the ~22,000 needed to pull everything.

WHAT COMES OUT
--------------
landscape.json
    field      a thinned background sample, so the map has a shape
    retracted  every retracted paper found, kept in full
    cells      a coarse grid with, per cell, how many papers were seen
               and how many of them were retracted

The cells are the point. A retraction rate per neighbourhood is the
measurable version of "some areas of the graph are riskier to sit in".

    ./venv/bin/python fetch_landscape.py --depth 5

Needs pyarrow, which is why this lives outside the page's own
dependencies: the deliverable stays vanilla JS reading plain JSON.
"""

import argparse
import gzip
import io
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pyarrow.feather as feather

BASE = "https://static.nomic.ai/tiles/pubmed"
CACHE = "landscape_cache"

_lock = threading.Lock()


def fetch(path, tries=4):
    """One tile or sidecar, gunzipped, cached on disk."""
    local = os.path.join(CACHE, path.replace("/", "_"))
    if os.path.exists(local):
        with open(local, "rb") as fh:
            return fh.read()

    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                f"{BASE}/{path}", headers={"User-Agent": "afterlife-hophacks/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)

    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    os.makedirs(CACHE, exist_ok=True)
    with open(local, "wb") as fh:
        fh.write(raw)
    return raw


def read(path):
    raw = fetch(path)
    if raw is None:
        return None
    try:
        return feather.read_table(io.BytesIO(raw))
    except Exception:
        return None


def load_tile(coord):
    """
    One tile plus the two sidecars we care about.

    A sidecar is a separate file with the same number of rows in the
    same order, so they are zipped together positionally. If a sidecar
    is missing the column simply comes back as all-None.
    """
    main = read(f"{coord}.feather")
    if main is None:
        return None, []

    n = main.num_rows
    cols = {c: main.column(c).to_pylist() for c in ("x", "y", "year") if c in main.schema.names}

    def sidecar(name):
        t = read(f"{coord}.{name}.feather")
        if t is None or t.num_rows != n:
            return [None] * n
        return t.column(0).to_pylist()

    retracted = sidecar("retracted")
    cites = sidecar("citation_count")

    rows = []
    for i in range(n):
        x, y = cols.get("x", [None] * n)[i], cols.get("y", [None] * n)[i]
        if x is None or y is None:
            continue
        rows.append((x, y, cols.get("year", [None] * n)[i], retracted[i], cites[i]))

    children = []
    md = main.schema.metadata or {}
    if b"children" in md:
        children = json.loads(md[b"children"].decode())

    return rows, children


def subject_labels():
    """
    The subject names Nomic places on the map, with their positions.

    A separate file from the tiles, and the only thing in the whole
    dataset that says what a region of the map is ABOUT. Without it a
    cluster of retractions is just a cluster; with it you can say
    which field it sits in.

    The weight is how many papers the label covers, and it matters
    for lookup: the map has 94 labels over 38 subjects, so several
    regions share a name, and the nearest label by raw distance is
    often a tiny one rather than the big region a point really
    belongs to.
    """
    raw = fetch("labels.geojson")
    if raw is None:
        return []
    gj = json.loads(raw.decode("utf8"))
    out = [{"t": f["properties"]["labels"],
            "x": round(f["geometry"]["coordinates"][0], 1),
            "y": round(f["geometry"]["coordinates"][1], 1),
            "n": int(f["properties"]["count"])}
           for f in gj["features"]]
    out.sort(key=lambda l: -l["n"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--depth", type=int, default=5,
                    help="quadtree depth to crawl (each level is ~4x the work)")
    ap.add_argument("--grid", type=int, default=60,
                    help="grid resolution for the per-neighbourhood rate")
    ap.add_argument("--field", type=int, default=40000,
                    help="background points to keep in the output")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="landscape.json")
    args = ap.parse_args()

    all_rows = []
    frontier = ["0/0/0"]
    seen = set()

    for depth in range(args.depth + 1):
        frontier = [c for c in frontier if c not in seen]
        if not frontier:
            break
        seen.update(frontier)

        nxt = []
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for rows, children in pool.map(load_tile, frontier):
                if rows:
                    all_rows.extend(rows)
                nxt.extend(children)
                done += 1
                if done % 100 == 0 or done == len(frontier):
                    print(f"  depth {depth}: {done}/{len(frontier)} tiles, "
                          f"{len(all_rows):,} papers", file=sys.stderr)
        frontier = nxt

    print(f"\n  {len(all_rows):,} papers sampled", file=sys.stderr)

    retracted = [r for r in all_rows if r[3]]
    print(f"  {len(retracted):,} of them retracted "
          f"({100*len(retracted)/max(1,len(all_rows)):.3f}%)", file=sys.stderr)

    if not all_rows:
        raise SystemExit("no data")

    xs = [r[0] for r in all_rows]
    ys = [r[1] for r in all_rows]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    # Per-neighbourhood retraction rate. A cell is only reported once it
    # holds enough papers for a rate to mean anything; one retraction in
    # a cell of three papers is noise, not a risky neighbourhood.
    G = args.grid
    cells = {}
    for x, y, year, retr, cites in all_rows:
        gx = min(G - 1, int((x - x0) / (x1 - x0) * G))
        gy = min(G - 1, int((y - y0) / (y1 - y0) * G))
        c = cells.setdefault((gx, gy), [0, 0])
        c[0] += 1
        if retr:
            c[1] += 1

    MIN_N = 40
    cell_out = [{"gx": gx, "gy": gy, "n": n, "r": r}
                for (gx, gy), (n, r) in sorted(cells.items()) if n >= MIN_N]

    rates = sorted((c["r"] / c["n"]) for c in cell_out)
    hot = sum(1 for c in cell_out if c["r"] / c["n"] >= 0.01)

    # Thin the background. The map's shape needs density, not every point.
    step = max(1, len(all_rows) // args.field)
    field = [[round(r[0], 1), round(r[1], 1)] for r in all_rows[::step]]

    out = {
        "source": "Nomic PubMed landscape, 20,672,357 papers",
        "sampled": len(all_rows),
        "retracted_found": len(retracted),
        "extent": {"x": [x0, x1], "y": [y0, y1]},
        "grid": G,
        "field": field,
        "retracted": [[round(r[0], 2), round(r[1], 2), int(r[2] or 0)] for r in retracted],
        "cells": cell_out,
        "labels": subject_labels(),
    }
    json.dump(out, open(args.out, "w"))

    print(f"\n  wrote {args.out} "
          f"({os.path.getsize(args.out)/1024/1024:.1f} MB)", file=sys.stderr)
    print(f"  background points kept : {len(field):,}", file=sys.stderr)
    print(f"  grid cells with n>={MIN_N}  : {len(cell_out):,}", file=sys.stderr)
    if rates:
        print(f"  retraction rate median : {rates[len(rates)//2]*100:.3f}%",
              file=sys.stderr)
        print(f"  worst cell             : {rates[-1]*100:.2f}%", file=sys.stderr)
        print(f"  cells at >=1% retracted: {hot}", file=sys.stderr)
        print(f"\n  If the worst neighbourhoods run orders of magnitude above\n"
              f"  the median, that is retraction behaving like a property of\n"
              f"  a POSITION rather than of a paper.", file=sys.stderr)


if __name__ == "__main__":
    main()
