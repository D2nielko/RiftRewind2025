"""
Grounded answer generation with Cohere Command (command-a).

Takes the reranked top-5 chunks, formats them as numbered, cited sources, and
asks command-a to answer the player's question using only those sources. The
prompt forces inline citations like [S1] so the UI can show which matches and
docs backed each claim — the whole point of the "grounded, cited" story.
"""

from typing import Dict, List

CHAT_MODEL = "command-a-03-2025"

SYSTEM_PREAMBLE = (
    "You are a League of Legends coach. Answer the player's question using ONLY "
    "the numbered sources provided. Sources tagged [match] are the player's own "
    "recent games (YAML records); sources tagged [champion]/[item]/[patch] are "
    "reference docs. Cite every claim inline with the source tag, e.g. [S1], "
    "[S3]. If the sources don't support an answer, say so plainly rather than "
    "guessing. Be specific and actionable: name champions, items, and numbers "
    "from the sources. Keep it to a few tight paragraphs."
)


def _format_sources(chunks: List[Dict]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(
            f"[S{i}] ({c['type']}) {c.get('title', '')}\n{c['text'].strip()}"
        )
    return "\n\n".join(blocks)


def answer(client, query: str, chunks: List[Dict]) -> Dict:
    """Generate a grounded answer; return text plus the cited source list."""
    if not chunks:
        return {
            "answer": "I couldn't find any relevant matches or docs for that. "
            "Try rephrasing, or make sure the corpus has been built.",
            "sources": [],
        }

    sources = _format_sources(chunks)
    user_msg = (
        f"Player question: {query}\n\n"
        f"Sources:\n{sources}\n\n"
        "Answer the question grounded in these sources, with inline [S#] citations."
    )

    resp = client.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PREAMBLE},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
    )

    text = resp.message.content[0].text

    return {
        "answer": text,
        "sources": [
            {
                "tag": f"S{i}",
                "id": c["id"],
                "type": c["type"],
                "title": c.get("title", ""),
                "rerank_score": round(c.get("rerank_score", 0), 3),
            }
            for i, c in enumerate(chunks, start=1)
        ],
    }
