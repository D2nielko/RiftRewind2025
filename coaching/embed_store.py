"""
Embedding store with on-disk caching.

The corpus (match records + Data Dragon docs) is embedded once with Cohere
embed-v4.0 and cached to disk keyed by a content hash, so re-running the app
doesn't re-embed unchanged chunks. This is the same cost/latency instinct as the
cost-routing in the companion ML project: embedding is the expensive, cacheable
step, so we pay for it exactly once per unique chunk.

Cache layout (coaching/cache/):
  embeddings.npz   - float32 matrix of vectors, row-aligned to ids.json order
  ids.json         - list of {id, hash} so we can detect changed chunks
  chunks.json      - the chunk payloads themselves (text/title/type/metadata)
"""

import hashlib
import json
import os
from typing import Dict, List, Tuple

import numpy as np

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
EMB_PATH = os.path.join(CACHE_DIR, "embeddings.npz")
IDS_PATH = os.path.join(CACHE_DIR, "ids.json")
CHUNKS_PATH = os.path.join(CACHE_DIR, "chunks.json")

EMBED_MODEL = "embed-v4.0"
# embed-v4.0 batch ceiling is 96 docs; stay under it.
BATCH = 96


def _chunk_hash(chunk: Dict) -> str:
    return hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()[:16]


def _embed_texts(client, texts: List[str], input_type: str) -> np.ndarray:
    """Embed a list of texts, batching to respect API limits."""
    vectors: List[List[float]] = []
    for start in range(0, len(texts), BATCH):
        batch = texts[start : start + BATCH]
        resp = client.embed(
            texts=batch,
            model=EMBED_MODEL,
            input_type=input_type,
            embedding_types=["float"],
        )
        # SDK exposes the "float" embedding list as the attribute `float_`.
        vectors.extend(resp.embeddings.float_)
    return np.asarray(vectors, dtype=np.float32)


def embed_query(client, query: str) -> np.ndarray:
    """Embed a single search query (input_type=search_query)."""
    vec = _embed_texts(client, [query], input_type="search_query")
    return vec[0]


class EmbeddingStore:
    """Holds the corpus + its vectors, persisting embeddings across runs."""

    def __init__(self):
        self.chunks: List[Dict] = []
        self.vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)

    # ---- persistence -----------------------------------------------------

    def _load_cache(self) -> Dict[str, np.ndarray]:
        """Return {hash: vector} for any cached chunks still on disk."""
        if not (os.path.exists(EMB_PATH) and os.path.exists(IDS_PATH)):
            return {}
        ids = json.load(open(IDS_PATH))
        mat = np.load(EMB_PATH)["v"]
        return {entry["hash"]: mat[i] for i, entry in enumerate(ids)}

    def _save_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        ids = [{"id": c["id"], "hash": _chunk_hash(c)} for c in self.chunks]
        json.dump(ids, open(IDS_PATH, "w"))
        json.dump(self.chunks, open(CHUNKS_PATH, "w"))
        np.savez_compressed(EMB_PATH, v=self.vectors)

    # ---- build -----------------------------------------------------------

    def build(self, client, chunks: List[Dict]) -> Tuple[int, int]:
        """
        Embed `chunks`, reusing cached vectors for unchanged text.

        Returns (n_reused, n_embedded) for cost visibility.
        """
        cached = self._load_cache()
        self.chunks = chunks

        to_embed_idx, to_embed_text = [], []
        vectors: List[np.ndarray] = [None] * len(chunks)

        for i, chunk in enumerate(chunks):
            h = _chunk_hash(chunk)
            if h in cached:
                vectors[i] = cached[h]
            else:
                to_embed_idx.append(i)
                to_embed_text.append(chunk["text"])

        if to_embed_text:
            fresh = _embed_texts(client, to_embed_text, input_type="search_document")
            for slot, vec in zip(to_embed_idx, fresh):
                vectors[slot] = vec

        self.vectors = np.vstack(vectors).astype(np.float32)
        self._save_cache()
        return len(chunks) - len(to_embed_idx), len(to_embed_idx)

    @classmethod
    def load(cls) -> "EmbeddingStore":
        """Load a previously built store without any API calls."""
        store = cls()
        if not os.path.exists(CHUNKS_PATH):
            raise FileNotFoundError("No cached corpus. Run build() first.")
        store.chunks = json.load(open(CHUNKS_PATH))
        store.vectors = np.load(EMB_PATH)["v"].astype(np.float32)
        return store

    # ---- search ----------------------------------------------------------

    def cosine_top_k(self, query_vec: np.ndarray, k: int = 50) -> List[Dict]:
        """Return the top-k chunks by cosine similarity to query_vec."""
        if self.vectors.shape[0] == 0:
            return []
        norms = np.linalg.norm(self.vectors, axis=1) * (np.linalg.norm(query_vec) + 1e-9)
        sims = (self.vectors @ query_vec) / (norms + 1e-9)
        top = np.argsort(-sims)[:k]
        out = []
        for idx in top:
            chunk = dict(self.chunks[idx])
            chunk["cosine"] = float(sims[idx])
            out.append(chunk)
        return out
