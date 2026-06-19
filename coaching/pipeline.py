"""
Corpus build + query orchestration.

build_corpus(): fetch the player's recent matches + Data Dragon docs, embed them
once (cached), and persist the store. Run this offline / on first launch.

answer_query(): load the cached store and run embed -> cosine top-50 ->
rerank-v3.5 top-5 -> command-a. No re-embedding of the corpus.

Run as a script to build the cache:
    python -m coaching.pipeline build --game-name Faker --tag-line KR1 --region KR
"""

import argparse
import os
from typing import Dict, List

# Load .env so the CLI (python -m coaching.pipeline) picks up RIOT_API_KEY /
# COHERE_API_KEY without an explicit export, matching app.py.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import cohere

from . import ddragon
from .coach import answer as generate_answer
from .embed_store import EmbeddingStore
from .match_ingest import fetch_match_chunks
from .retriever import retrieve

# Region -> Riot platform/routing (mirrors app.py's REGION_MAPPINGS).
REGION_MAPPINGS = {
    "NA": {"platform": "na1", "routing": "americas"},
    "EUW": {"platform": "euw1", "routing": "europe"},
    "EUNE": {"platform": "eun1", "routing": "europe"},
    "KR": {"platform": "kr", "routing": "asia"},
    "BR": {"platform": "br1", "routing": "americas"},
    "JP": {"platform": "jp1", "routing": "asia"},
    "OCE": {"platform": "oc1", "routing": "americas"},
}


def _cohere_client() -> cohere.ClientV2:
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        raise RuntimeError("COHERE_API_KEY not set.")
    return cohere.ClientV2(api_key=key)


def build_corpus(
    game_name: str,
    tag_line: str,
    region: str = "NA",
    match_count: int = 20,
    patch: str = None,
) -> Dict:
    """Fetch matches + docs, embed once (cached), persist the store."""
    riot_key = os.environ.get("RIOT_API_KEY")
    if not riot_key:
        raise RuntimeError("RIOT_API_KEY not set.")

    region_cfg = REGION_MAPPINGS.get(region, REGION_MAPPINGS["NA"])
    patch = patch or ddragon.latest_patch()

    # Data Dragon docs (champions/items/patch) + item-id->name map for builds.
    doc_chunks = ddragon.build_ddragon_corpus(patch=patch)
    item_names = ddragon.item_id_to_name(patch=patch)

    match_chunks = fetch_match_chunks(
        api_key=riot_key,
        game_name=game_name,
        tag_line=tag_line,
        routing=region_cfg["routing"],
        platform=region_cfg["platform"],
        count=match_count,
        item_names=item_names,
    )

    chunks: List[Dict] = match_chunks + doc_chunks
    client = _cohere_client()
    store = EmbeddingStore()
    reused, embedded = store.build(client, chunks)

    return {
        "patch": patch,
        "match_chunks": len(match_chunks),
        "doc_chunks": len(doc_chunks),
        "total_chunks": len(chunks),
        "vectors_reused": reused,
        "vectors_embedded": embedded,
    }


def answer_query(query: str) -> Dict:
    """Load cached store, retrieve, and produce a grounded answer."""
    client = _cohere_client()
    store = EmbeddingStore.load()
    chunks = retrieve(client, store, query)
    return generate_answer(client, query, chunks)


def main():
    parser = argparse.ArgumentParser(description="LoL coaching corpus pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build & cache the corpus")
    b.add_argument("--game-name", required=True)
    b.add_argument("--tag-line", required=True)
    b.add_argument("--region", default="NA")
    b.add_argument("--match-count", type=int, default=20)

    q = sub.add_parser("ask", help="Ask a question against the cached corpus")
    q.add_argument("query")

    args = parser.parse_args()
    if args.cmd == "build":
        stats = build_corpus(
            args.game_name, args.tag_line, args.region, args.match_count
        )
        print("Corpus built:", stats)
    elif args.cmd == "ask":
        result = answer_query(args.query)
        print(result["answer"])
        print("\nSources:")
        for s in result["sources"]:
            print(f"  [{s['tag']}] {s['type']}: {s['title']} ({s['rerank_score']})")


if __name__ == "__main__":
    main()
