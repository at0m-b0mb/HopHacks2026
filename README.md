<div align="center">

<img src="banner.svg" alt="Afterlife — retraction is supposed to kill a paper. It doesn't — it slows it." width="100%">

<br><br>

![Track](https://img.shields.io/badge/HopHacks_2026-Memetics-B02A1F?style=flat-square&labelColor=1F1A15)
![Papers](https://img.shields.io/badge/retracted_papers-300-1F1A15?style=flat-square&labelColor=D6CCB8)
![Citations](https://img.shields.io/badge/citations_measured-144%2C992-1F1A15?style=flat-square&labelColor=D6CCB8)
![Map](https://img.shields.io/badge/map_sampled-3.4M_papers-1F1A15?style=flat-square&labelColor=D6CCB8)
![Stack](https://img.shields.io/badge/vanilla_JS-no_build_step-6B6154?style=flat-square&labelColor=D6CCB8)

**Kailash Parshad** · **Ilaqquan Rajesh Indure**

</div>

---

A retraction is a dated, public statement that a result should no longer be
treated as knowledge. **Afterlife** measures what happens to the citations
afterwards.

```bash
python3 -m http.server 5173     # then open http://localhost:5173
```

> [!NOTE]
> It has to be served over HTTP. The page fetches three JSON files, and a
> `file://` page treats each one as a separate origin and blocks the request.

<br>

## ◆ The finding

<div align="center">

| | | |
|:--:|:--:|:--:|
| **63%** | **177 / 300** | **0.62×** |
| of all citations arrived<br>*after* the retraction | papers cited more after<br>withdrawal than before | but the median paper's<br>citation **rate** after ÷ before |

</div>

<img src="images/1-one-paper.jpg" alt="One paper's citations, grey before the retraction and red after, with the readout open on 2019" width="100%">

91,713 of 144,992 citations to these 300 retracted papers arrived after the
paper was withdrawn.

**The third number is the one to lead with**, and it is the reason to trust
the rest. The median paper here spent 2 years valid and 5 years retracted, so
it simply had longer to accumulate posthumous citations. Normalise for that
and the median paper's citation rate falls to **0.62×** — and **63 of 205**
papers are cited *faster* per year after being withdrawn than before.

> Retraction cuts the citation rate by about a third.
> It does not stop it. Roughly a third of papers accelerate.

<img src="images/4-the-number.jpg" alt="Citation rate before retraction against rate after on log axes, with the diagonal where nothing changed and the 0.62x median line below it" width="100%">

That version survives the first hard question. "Retraction has no effect"
does not.

<br>

## ◆ The part nobody has measured

Everything published on this counts the **first ring** — papers citing the
retracted paper directly. Those authors at least had it in their hands.

The **second ring** is papers citing one of *those*. Their authors have no
reason to know a retraction sits anywhere in their reference chain.

For the featured paper — *A Comprehensive Review on Metabolic Syndrome*,
published 2014, retracted 2019:

| | distinct works | after retraction |
|---|--:|--:|
| **ring 1** — cite it directly | 1,888 | 947 |
| **ring 2** — cite something that cites it | **57,765** | **52,341** |

<img src="images/3-two-rings.jpg" alt="Two ring series drawn at the same scale, with the readout on 2026 showing 396 second-hand citations per direct one" width="100%">

Per year, the two rings move in **opposite directions**. Counting
transmission paths, direct citation peaks at 307 a year in 2018 and **falls
to 12** by 2026. Second-hand citation is 2,926 in 2018 and **climbs to
9,318** by 2024. The year before retraction there were 10 second-hand
citations for every direct one. By 2026 there are **396**.

> The correction reaches the first ring. It never reaches the second.

<br>

## ◆ Where in science this happens

| | |
|---|--:|
| baseline retraction rate across the map | **0.057%** |
| worst neighbourhood | **10.7%** — 188× the average |
| share of the map holding half of all retractions | **4.3%** (109 of 2,523 cells) |
| neighbourhoods with no retractions at all | **1,700 of 2,523** |

<img src="images/2-the-map.jpg" alt="3.4 million papers placed by subject, with the readout naming the worst neighbourhood as pharmacology at 10.7%" width="100%">

Hovering the worst one names it: **pharmacology**.

That is retraction behaving partly like a property of a *position* rather
than of a paper.

<br>

## ◆ What you are looking at

The page is one continuous scroll. Four views, each answering the next
question the previous one raises. Scrolling settles on a view rather
than stopping halfway between two, so the picture is never cut in half
by the edge of the screen.

| | view | the question it answers | hover gives you | link |
|:--:|---|---|---|---|
| **1** | **One paper** | When did its citations arrive, relative to the retraction? | the year, the count, and which side of the line it fell on | `#paper` |
| **2** | **The map** | Is this everywhere, or somewhere? | the neighbourhood's subject, papers sampled, and its retraction rate | `#map` |
| **3** | **Two rings** | Does the correction reach the people downstream? | the year, both rings' counts, and the ratio between them | `#rings` |
| **4** | **Rate before vs after** | Once you divide by the time available, what did retraction actually do? | the paper, both of its rates, and the ratio | `#rates` |

Each view answers to its own URL, so the writeup and the demo can point
straight at the second ring instead of asking someone to scroll and
hope.

**The first view is not one cherry-picked paper.** The chevrons either
side of Play step through all 300 — by tap or by arrow key — and the
line beneath says which one you are on. Every paper in `papers.json`
draws the same way.

**It can also read itself aloud.** One recording per view, so the audio
follows the reader down the page rather than running on its own clock.
Off by default; the Listen control only appears when the audio files
are present.

<br>

## ◆ What we deliberately do not claim

Say these before anyone asks. They are why the rest is trustworthy.

- **Retracted is not fraudulent.** Some of these are honest error or
  retract-and-replace. The data records a withdrawal, not a verdict on the
  authors.
- **The second ring is reachability, not influence.** A paper citing a paper
  that cited a retracted one may be citing its source for something entirely
  unrelated.
- **The second ring is also structurally later in time**, so part of its very
  high posthumous share is lag rather than contagion.
- **Paths are not works.** 65,736 transmission paths reach the second ring;
  57,765 *distinct works* do. A work inheriting the claim by three routes is
  counted three times in the first figure and once in the second. The two are
  never mixed, and 2026 is a partial year wherever it appears.
- **The page prints the totals its columns actually add to.** The ring view
  shows **65,629** paths, not 65,736: the columns can only cover the years
  OpenAlex reports per year, which is roughly 2012 on. The same 15-year
  window described below.
- **Two counts of the same paper's direct citations, from two queries.**
  The `cites:` query returns **1,888** distinct citing works; the paper's own
  `counts_by_year` records **1,886** citations. Five of the tree's 1,888 were
  published in 1970, 2000 and 2010 and cannot have cited a 2014 paper, so the
  citation-graph side is the less trustworthy — though removing them gives
  1,883, not 1,886, so the rest is ordinary drift between two snapshots. Both
  views in the page read the direct series from `papers.json`, so the figure
  is the same wherever you meet it; the 1,888 above is the distinct-works
  count from `contagion_hero.json`, which is a different measurement.
- **The map is topical, not social.** It is built from text similarity, so it
  shows that some *subjects* are far riskier than others — not that some
  research groups are. Those are different graphs.
- **Area on screen is not count.** In the first view later citations sweep
  across more space than earlier ones. The number in the corner is the
  quantity; the ink is not.
- **The sample is the most-cited retracted papers**, not a random draw. Papers
  nobody cited either way carry no signal, but it is a sampling choice and
  not a neutral one.

<br>

## ◆ The data

Three sources, because no single one has what this needs.

<table>
<tr><td width="33%" valign="top">

**OpenAlex**<br>
*which papers are retracted,<br>and citations per year*

`is_retracted`, `counts_by_year`,
and who cites whom via the
`cites:` filter.

</td><td width="33%" valign="top">

**Crossref**<br>
*when each paper<br>was retracted*

Retraction Watch's dates, on the
*original* work's record under
`updated-by`.

</td><td width="33%" valign="top">

**Nomic PubMed**<br>
*where each paper sits*

20,672,357 papers embedded in
2D by text similarity, as a
quadtree of Arrow tiles.

</td></tr>
</table>

OpenAlex **does not record when a paper was retracted** — there is no such
field. Without a date there is no before and no after, and this project does
not exist. Joining it to Crossref is the hinge the whole thing turns on.

### The constraint that keeps it honest

OpenAlex reports citations per year only for roughly the last fifteen years.
Ask it about a 1998 paper and you get 2012 onward — we measured one missing
**1,159 citations, every one of them pre-retraction**.

Including those papers would have inflated the posthumous share *in our own
favour*. So the pipeline **refuses any paper published before that window
opens**, and then checks each survivor: its per-year counts must reconcile
with its headline `cited_by_count` or it is dropped and reported. That is why
the data starts in 2012 rather than 1995.

<br>

## ◆ Files

| file | what it is |
|---|---|
| `index.html` | the whole page — vanilla JS, no build step, no dependencies |
| `banner.svg` | the mark at the top of this file, drawn from the same rules as the page |
| `og.png` | the link preview, rendered from that banner |
| `images/*.jpg` | the four views above, captured from the live page with the readouts open |
| `favicon.svg` | the tab mark: an axis, a publication dot, a retraction |
| `papers.json` | 300 retracted papers with citations per year |
| `landscape.json` | 3.4M paper positions, 1,925 retracted, per-neighbourhood rates, 94 subject labels |
| `tree_hero.json` | the featured paper's two-generation transmission tree |
| `contagion_hero.json` | deduplicated ring-1 / ring-2 counts for the featured paper |
| `contagion_sample.json` | the same for a sample of 11 papers |
| `fetch_papers.py` | builds `papers.json` from OpenAlex + Crossref |
| `fetch_contagion.py` | counts the second ring, deduplicated as a set of work ids |
| `fetch_tree.py` | the drawable two-generation tree for one paper |
| `fetch_landscape.py` | crawls the Nomic map (needs `pyarrow`) |
| `narration/*.txt` | what the page says out loud, one file per view |
| `make_narration.py` | renders those to `audio/*.mp3` via ElevenLabs |

The page fetches only `papers.json`, `tree_hero.json` and `landscape.json`.
**No API call happens at view time** — it runs with no network at all, apart
from Google Fonts. The two `contagion_*.json` files are the deduplicated
counts the README and the page copy quote; they are evidence, not runtime
data.

### Regenerating

```bash
export OPENALEX_KEY=...        # free: help.openalex.org/api/authentication
python3 fetch_papers.py    --target 300 --min-citations 60
python3 fetch_contagion.py W2144590229 --out contagion_hero.json
python3 fetch_tree.py      W2144590229 --out tree_hero.json

python3 -m venv venv && ./venv/bin/pip install pyarrow
./venv/bin/python fetch_landscape.py --depth 3
```

The page can also read itself aloud, one recording per view:

```bash
export ELEVENLABS_API_KEY=...
python3 make_narration.py --voices          # pick one
python3 make_narration.py --voice <voice_id>
```

That writes `audio/`. The Listen control only appears if those files
are present, so a clone without an API key gets the page in silence
rather than a button that does nothing.

A key is worth the minute it takes. Without one, requests count against a
daily budget shared by everyone on your IP address, and we exhausted it.
`pyarrow` is needed only by `fetch_landscape.py`, to read the map's Arrow
tiles — a build-time dependency. The page itself has none.

<br>

## ◆ How the page is built

One HTML file. Canvas for the marks — there are thousands of them and SVG
would not keep up — and real DOM for every piece of type, so the browser
kerns and wraps it properly. Scroll position is the only thing that changes
the view, so the text and the picture can never disagree about which one you
are looking at.

A few decisions worth being able to defend:

- **One line per real citation.** A paper cited 1,886 times draws 1,886
  lines. Nothing is capped or rescaled to fit, because two papers with very
  different citation counts must not produce the same picture.
- **The counter counts; it does not interpolate.** It tallies the marks
  actually on screen using the same `>=` test that colours them, which is why
  it lands on exactly `citations_after` rather than near it.
- **The retraction year counts as after.** One rule, fixed before any code
  was written, living in exactly one place in each file.
- **Colour is decided by the integer year, never by drawn position.**
  Citations are scattered within their year so the columns are not hard
  rules, but that scatter is a drawing device and must not be able to push a
  citation across the boundary.
- **Arcs are split at the retraction by clipping the canvas.** An arc from
  2024 flies back over the valid years to reach the publication dot; painting
  it red along its whole length would colour a period when that citation had
  not happened yet. The banner above is drawn the same way.
- **Every landing is punched out of the arcs beneath it.** A dot drawn in
  its own trail's colour disappears into a thousand crossing arcs. The
  dots are the data; the arcs are only how it travelled, so the dots win.
- **The rate view is drawn square, with one scale on both axes.** The
  whole reading is above or below the diagonal, and a diagonal that is
  not at 45° quietly moves papers across it.
- **A step's copy has to fit the screen.** Text running past the fold
  means reading with the picture gone, which is the one thing this
  cannot afford: the words and the thing they describe have to be
  visible together. On a short screen the type steps down rather than
  the copy being cut.
- **Snapping is `proximity`, not `mandatory`.** Mandatory refuses to
  leave a snap point until you pass its midpoint, which on a short
  screen can hold a reader against a paragraph they cannot finish.

### The palette

| | | |
|---|---|---|
| ![](https://img.shields.io/badge/-F1EBDF-F1EBDF?style=flat-square) `#F1EBDF` | paper | the field everything sits on |
| ![](https://img.shields.io/badge/-1F1A15-1F1A15?style=flat-square) `#1F1A15` | ink | type, and the publication dot |
| ![](https://img.shields.io/badge/-6B6154-6B6154?style=flat-square) `#6B6154` | soft ink | secondary type |
| ![](https://img.shields.io/badge/-B9AE9C-B9AE9C?style=flat-square) `#B9AE9C` | faded | citations before the retraction |
| ![](https://img.shields.io/badge/-D6CCB8-D6CCB8?style=flat-square) `#D6CCB8` | rule | axes and dividers |
| ![](https://img.shields.io/badge/-B02A1F-B02A1F?style=flat-square) `#B02A1F` | stamp | the retraction, and everything after it |

Instrument Serif for display, Spectral for reading, Courier Prime for
anything that is a measurement.

<br>

---

<div align="center">

Data from **[OpenAlex](https://openalex.org)** · retraction dates from
**[Retraction Watch](https://retractionwatch.com)** via
**[Crossref](https://crossref.org)** · map from the
**[Nomic PubMed landscape](https://static.nomic.ai/pubmed.html)**

*Every figure on the page and in this file is computed from the data files in
this repository. None of them are typed in by hand.*

</div>
