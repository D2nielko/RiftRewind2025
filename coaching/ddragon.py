"""
Data Dragon corpus builder.

Pulls champion and item data (and a small hand-written patch-context blurb) from
Riot's Data Dragon CDN and turns them into a few hundred text chunks. These are
the static "docs" side of the retrieval: when a user asks "what do I build into
an AD-heavy team", the reranker should surface the relevant item chunks (armor
items, etc.) alongside their recent matches.

Data Dragon is public (no API key) and versioned by patch, so the chunks are
deterministic for a given patch and cache cleanly.
"""

from typing import Dict, List

import requests

DDRAGON = "https://ddragon.leagueoflegends.com"


def latest_patch() -> str:
    versions = requests.get(f"{DDRAGON}/api/versions.json", timeout=10).json()
    return versions[0]


def _champion_chunks(patch: str, lang: str = "en_US") -> List[Dict]:
    data = requests.get(
        f"{DDRAGON}/cdn/{patch}/data/{lang}/champion.json", timeout=15
    ).json()["data"]

    chunks = []
    for name, c in data.items():
        tags = ", ".join(c.get("tags", []))
        info = c.get("info", {})
        text = (
            f"Champion: {c['name']} ({c['title']}). "
            f"Class: {tags}. Resource: {c.get('partype', 'N/A')}. "
            f"Difficulty rating {info.get('difficulty', '?')}/10, "
            f"attack {info.get('attack', '?')}, defense {info.get('defense', '?')}, "
            f"magic {info.get('magic', '?')}. "
            f"Playstyle blurb: {c.get('blurb', '').strip()}"
        )
        chunks.append(
            {
                "id": f"champion:{c['id']}",
                "type": "champion",
                "title": f"{c['name']} — {c['title']}",
                "text": text,
            }
        )
    return chunks


def _item_chunks(patch: str, lang: str = "en_US") -> List[Dict]:
    data = requests.get(
        f"{DDRAGON}/cdn/{patch}/data/{lang}/item.json", timeout=15
    ).json()["data"]

    chunks = []
    for iid, item in data.items():
        # Skip non-SR / consumable / trinket noise; keep purchasable combat items.
        maps = item.get("maps", {})
        if not maps.get("11"):  # Summoner's Rift
            continue
        gold = item.get("gold", {})
        if not gold.get("purchasable") or gold.get("total", 0) < 500:
            continue
        stats = ", ".join(f"{k}: {v}" for k, v in item.get("stats", {}).items())
        plain = item.get("plaintext", "")
        text = (
            f"Item: {item['name']} (cost {gold.get('total', '?')}g). "
            f"{plain}. Stats: {stats or 'see description'}. "
            f"Tags: {', '.join(item.get('tags', []))}."
        )
        chunks.append(
            {
                "id": f"item:{iid}",
                "type": "item",
                "title": item["name"],
                "text": text,
                "name": item["name"],
            }
        )
    return chunks


def _patch_chunks(patch: str) -> List[Dict]:
    """A small grounding chunk so the model can cite the active patch."""
    return [
        {
            "id": f"patch:{patch}",
            "type": "patch",
            "title": f"Patch {patch} context",
            "text": (
                f"The active League of Legends patch is {patch}. Match records and "
                f"item/champion data in this corpus reflect patch {patch}. When giving "
                f"build or matchup advice, prefer items and interactions valid on this patch."
            ),
        }
    ]


def build_ddragon_corpus(patch: str = None) -> List[Dict]:
    patch = patch or latest_patch()
    chunks = []
    chunks.extend(_patch_chunks(patch))
    chunks.extend(_champion_chunks(patch))
    chunks.extend(_item_chunks(patch))
    return chunks


def item_id_to_name(patch: str = None, lang: str = "en_US") -> Dict[int, str]:
    """Map numeric item IDs -> names so match builds read as item names."""
    patch = patch or latest_patch()
    data = requests.get(
        f"{DDRAGON}/cdn/{patch}/data/{lang}/item.json", timeout=15
    ).json()["data"]
    return {int(iid): item["name"] for iid, item in data.items()}
