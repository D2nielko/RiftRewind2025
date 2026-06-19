# RiftRewind Coach — Cohere retrieval layer

A natural-language coaching tool layered on top of the existing RiftRewind ML
app. It reuses this project's Riot API ingestion and Flask/AWS deployment, and
adds a two-stage retrieval pipeline so a user can ask:

- *"Why am I losing mid lane?"*
- *"What should I build into an AD-heavy enemy team?"*
- *"Which of my recent games was my best performance and why?"*

…and get a **grounded answer that cites which of their matches and which
champion/item/patch docs it used.**

## Pipeline

```
query
  │  embed-v4.0 (search_query)
  ▼
cosine top-50          ← over a cached corpus of match records + Data Dragon docs
  │  rerank-v3.5
  ▼
rerank top-5
  │  command-a, sources-only prompt with inline [S#] citations
  ▼
grounded answer + cited sources
```

### Corpus
- **~20 recent matches** from the Riot API (`coaching/match_ingest.py`),
  reusing the project's `RiotDataCollector`. Each match is normalized to a
  compact **YAML** record (lane matchup, build, economy/combat deltas, team
  comps). YAML is deliberate: Cohere Rerank handles semi-structured documents
  well, and the inline field names act as match-able tokens for queries like
  "mid lane" or a champion name.
- **~400 Data Dragon chunks** (`coaching/ddragon.py`): one per champion (~172)
  and per purchasable SR item (~212), plus a patch-context chunk. Public CDN,
  no key, versioned by patch.

### Embedding cache (cost/latency)
`coaching/embed_store.py` embeds the corpus **once** with `embed-v4.0` and caches
the vectors to `coaching/cache/` keyed by a content hash. Re-runs reuse cached
vectors for unchanged chunks and only embed new/changed ones — the same
cost-routing instinct as the companion ML project. Search and answer load the
cache with **zero embedding calls** for the corpus.

## Usage

```bash
export RIOT_API_KEY=...      # already used by the base app
export COHERE_API_KEY=...

# 1. Build & cache the corpus (offline, run once per player/patch)
python -m coaching.pipeline build --game-name YOURNAME --tag-line NA1 --region NA

# 2a. Ask from the CLI
python -m coaching.pipeline ask "why am I losing mid lane?"

# 2b. …or use the web UI
python app.py     # then open http://localhost:5000/coach
```

The `/coach` page has the three preset queries as buttons; `/api/coach` runs the
retrieve→rerank→generate path and returns the answer plus the cited sources.

## Files
| File | Role |
|------|------|
| `match_ingest.py` | Riot matches → normalized YAML record chunks |
| `ddragon.py` | Data Dragon champion/item/patch → doc chunks |
| `embed_store.py` | `embed-v4.0` embedding + on-disk vector cache + cosine top-k |
| `retriever.py` | cosine top-50 → `rerank-v3.5` top-5 |
| `coach.py` | `command-a` grounded answer with `[S#]` citations |
| `pipeline.py` | `build_corpus()` / `answer_query()` orchestration + CLI |

## Models
- Embeddings: `embed-v4.0`
- Rerank: `rerank-v3.5`
- Generation: `command-a-03-2025`
