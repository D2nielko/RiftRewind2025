"""
Match ingestion for the coaching retriever.

Reuses the existing RiotDataCollector (ml_training/data_collection.py) to pull a
player's recent matches, then normalizes each into a compact record focused on
the things a coaching answer needs: lane matchup, build, economy/combat deltas,
and a short outcome summary. Records are emitted as YAML because Cohere Rerank
handles semi-structured text well, and YAML keeps the field names inline as
natural-language-ish tokens the reranker can match against a query.
"""

import os
import sys
from typing import Dict, List, Optional

import yaml

# Reuse the ingestion client from the ML project.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from ml_training.data_collection import RiotDataCollector  # noqa: E402

# Riot queueId -> human label (we only care about a few SR queues).
QUEUE_LABELS = {
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Normal Blind",
    440: "Ranked Flex",
    700: "Clash",
}


def _team_of(participant: Dict) -> int:
    return participant["teamId"]


def _lane_opponent(participant: Dict, participants: List[Dict]) -> Optional[Dict]:
    """Find the enemy in the same position (best-effort)."""
    pos = participant.get("teamPosition") or participant.get("individualPosition")
    if not pos or pos in ("Invalid", ""):
        return None
    for p in participants:
        if p["teamId"] != participant["teamId"] and (
            p.get("teamPosition") == pos or p.get("individualPosition") == pos
        ):
            return p
    return None


def _items(participant: Dict) -> List[int]:
    return [participant[f"item{i}"] for i in range(7) if participant.get(f"item{i}")]


def normalize_match(match: Dict, puuid: str, item_names: Dict[int, str] = None) -> Optional[Dict]:
    """Turn one raw match into a flat coaching record for the player `puuid`."""
    info = match.get("info", {})
    participants = info.get("participants", [])
    me = next((p for p in participants if p["puuid"] == puuid), None)
    if not me:
        return None

    duration_min = round(info["gameDuration"] / 60, 1)
    opp = _lane_opponent(me, participants)
    ch = me.get("challenges", {})
    item_names = item_names or {}

    def item_label(iid: int) -> str:
        return item_names.get(iid, str(iid))

    record = {
        "match_id": match["metadata"]["matchId"],
        "patch": ".".join(info.get("gameVersion", "").split(".")[:2]),
        "queue": QUEUE_LABELS.get(info.get("queueId"), str(info.get("queueId"))),
        "duration_min": duration_min,
        "champion": me["championName"],
        "role": me.get("teamPosition") or me.get("individualPosition"),
        "result": "WIN" if me["win"] else "LOSS",
        "kda": f"{me['kills']}/{me['deaths']}/{me['assists']}",
        "cs": me["totalMinionsKilled"] + me.get("neutralMinionsKilled", 0),
        "cs_per_min": round(
            (me["totalMinionsKilled"] + me.get("neutralMinionsKilled", 0)) / duration_min, 1
        ),
        "gold_per_min": round(me["goldEarned"] / duration_min),
        "damage_to_champs": me["totalDamageDealtToChampions"],
        "damage_share_pct": round(ch.get("teamDamagePercentage", 0) * 100),
        "kill_participation_pct": round(ch.get("killParticipation", 0) * 100),
        "vision_score": me["visionScore"],
        "solo_kills": ch.get("soloKills", 0),
        "deaths_to_ganks": ch.get("deathsByEnemyChamps", me["deaths"]),
        "build": [item_label(i) for i in _items(me)],
    }

    if opp:
        record["lane_opponent"] = {
            "champion": opp["championName"],
            "kda": f"{opp['kills']}/{opp['deaths']}/{opp['assists']}",
            "cs_diff_at_lane": round(ch.get("maxCsAdvantageOnLaneOpponent", 0)),
        }

    # Team comp context — useful for "what do I build into X" style queries.
    enemy_team = _team_of(me) ^ (100 ^ 200)  # flip 100<->200
    record["enemy_champions"] = [
        p["championName"] for p in participants if p["teamId"] == enemy_team
    ]
    record["ally_champions"] = [
        p["championName"]
        for p in participants
        if p["teamId"] == _team_of(me) and p["puuid"] != puuid
    ]
    return record


def record_to_chunk(record: Dict) -> Dict:
    """Wrap a normalized record as a corpus chunk (YAML text + metadata)."""
    text = yaml.safe_dump(record, sort_keys=False, default_flow_style=False)
    return {
        "id": f"match:{record['match_id']}",
        "type": "match",
        "title": f"{record['result']} as {record['champion']} ({record['role']}) — {record['match_id']}",
        "text": text,
    }


def fetch_match_chunks(
    api_key: str,
    game_name: str,
    tag_line: str,
    routing: str = "americas",
    platform: str = "na1",
    count: int = 20,
    item_names: Dict[int, str] = None,
) -> List[Dict]:
    """Resolve a Riot ID, pull recent matches, return them as corpus chunks."""
    import requests

    acct_url = (
        f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/"
        f"by-riot-id/{game_name}/{tag_line}"
    )
    resp = requests.get(acct_url, headers={"X-Riot-Token": api_key}, timeout=10)
    resp.raise_for_status()
    puuid = resp.json()["puuid"]

    collector = RiotDataCollector(api_key=api_key, region=platform, routing=routing)
    match_ids = collector.get_match_history(puuid, count=count)

    chunks = []
    for mid in match_ids:
        match = collector.get_match_details(mid)
        if not match:
            continue
        record = normalize_match(match, puuid, item_names=item_names)
        if record:
            chunks.append(record_to_chunk(record))
    return chunks
