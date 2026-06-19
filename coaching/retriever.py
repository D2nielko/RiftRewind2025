"""
Two-stage retrieval.

Stage 1 (recall): embed the query (embed-v4.0) and take cosine top-50 from the
cached corpus. Cheap and broad.

Stage 2 (precision): hand those 50 to Cohere rerank-v3.5, keep the top-5. The
reranker reads each chunk's text directly — including the YAML match records —
which is why match records are formatted as YAML rather than flattened prose:
rerank-v3.5 handles semi-structured documents well and can match query terms
("mid lane", "AD", a champion name) against inline field values.
"""

from typing import Dict, List

from .embed_store import EmbeddingStore, embed_query

RERANK_MODEL = "rerank-v3.5"


def retrieve(
    client,
    store: EmbeddingStore,
    query: str,
    cosine_k: int = 50,
    rerank_k: int = 5,
) -> List[Dict]:
    """Run cosine recall then rerank precision; return top chunks with scores."""
    qvec = embed_query(client, query)
    candidates = store.cosine_top_k(qvec, k=cosine_k)
    if not candidates:
        return []

    documents = [c["text"] for c in candidates]
    reranked = client.rerank(
        model=RERANK_MODEL,
        query=query,
        documents=documents,
        top_n=min(rerank_k, len(documents)),
    )

    results: List[Dict] = []
    for r in reranked.results:
        chunk = dict(candidates[r.index])
        chunk["rerank_score"] = float(r.relevance_score)
        results.append(chunk)
    return results
