# Vendor Maps source pipeline

Keeps the vendor list filling from public sources, the same way the Ohio Cannabis Ecosystem
Directory is built: every vendor traces to a named public list, with the date it was read and an
evidence level.

```
pipeline/registry.json -> sources  -> data/sources/<id>.json   (business fields only, dated, counted)
data/rosters/<id>.json  ->                                      (rosters read from public pages)
                           merge    -> data/vendors.json        (deduplicated; what the site shows)
                           coverage -> data/coverage.json + docs/COVERAGE.md (gaps and the queue)
index.html reads data/vendors.json.
```

## Run it cold

On GitHub: Actions → **Mine vendor sources** → Run workflow. Leave "only" blank for everything.
It re-pulls the automatic sources, re-normalizes the rosters, merges, runs the checks and commits
to `main`.

On a computer:

```bash
pip install -r pipeline/requirements.txt
python -m pipeline.run                       # everything active
python -m pipeline.run --only owner-         # just the owner's directories (id prefix)
python -m pipeline.run --offline             # no downloads: rebuild from committed files
python -m unittest discover -s tests -v      # privacy and shape checks (must pass before a push)
```

`CANNABIS_DIR=/path/to/ohio-cannabis-directory` makes the owner-directory sources read a local
checkout instead of downloading.

## Add a batch of event rosters

Most event lists are web pages written for people (prose, cards, PDFs, pictures), so the usual
way in is a reader: a person or an assistant opens the public page, copies the businesses into a
collection file (shape in `pipeline/add_rosters.py`), then:

```bash
python -m pipeline.add_rosters my-batch.json   # writes data/rosters/ and registry entries
python -m pipeline.run --offline
python -m unittest discover -s tests -v
```

Reading the same page again later replaces that roster; it does not duplicate it. Pages that were
blocked, or that need a later look, go in the collection's `blocked` and `leads` lists and land in
the registry as `blocked` or `queued`, so they show up in the coverage queue.

An event page with a clean list can be made automatic: set its `fetch.method` to `html-list` with
a CSS `selector` (one element per vendor) and the Actions run will re-pull it.

## Registry fields

| Field | Meaning |
| --- | --- |
| `id` | `us-<state>-<event>-<year>` for rosters, `owner-<name>` for the owner's directories; never reused |
| `jurisdiction` | the state the event is in |
| `title`, `publisher`, `landing_url` | what the list is and the public page anyone can check |
| `event` | name, year, city, state and type of the event (rosters) |
| `fetch` | `method` = `csv`, `json`, `html-list` or `roster`; `url`; for html-list a `selector` |
| `importer` | which function in `importers.py` reads it |
| `evidence_level` | one of `EVIDENCE_LEVELS` in `common.py` |
| `cadence_days` | how often to read it again (markets 90, festivals and fairs 180, owner directories 30) |
| `status` | `active`, `queued` (known, not read yet) or `blocked` (turned the reader away) |

## Rules the pipeline keeps

- **Public sources only.** No sign-ins, no accounts, no forms, no messages to anyone.
- **Business names only.** No contact people, emails or phone numbers are stored anywhere, even
  when a source publishes them. Entries that name only a person (common on artist lists) are
  counted, not listed. The checks fail if an email address, phone number or personal name gets
  into published data.
- **Contact is opt-in through Vendor Maps.** Websites stay in the snapshots; the site shows name,
  category, reach, place and the events a business was seen at.
- **A blocked page is not a review.** A 401/403/429, login wall or bot check is logged as
  blocked and left for a person. Nothing tries another route (no mirrors, caches or archives).
- **Dated, not live.** Every snapshot keeps the date read, where it was read, a SHA-256 of what
  was read and the counts kept and dropped.
- **We're not selling your data.**

## Scope (reach)

Worked out in `classify.py`, with the reason kept beside each vendor:

- **national**: the source says it serves the whole country, or it was seen in 4+ states
- **regional**: seen at events in 2 or 3 states
- **state**: the source says statewide, or it was seen in 2+ cities in one state
- **local**: one city or metro area
