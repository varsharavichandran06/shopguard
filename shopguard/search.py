"""Grounded policy search: BM25 (written by hand) + OpenAI embeddings, fused with RRF.

- Chunks are policy sections (split on "## " headings), each with a doc id for citing.
- Vectors are cached in data/policy_index.json so we embed each chunk only once.
- If there is no API key, search falls back to BM25 only and still works.
- A relevance floor returns NO_RELEVANT_POLICY instead of the least bad chunk.
"""
import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass

from .config import EMBED_MODEL, POLICY_DIR, POLICY_INDEX

RRF_K = 60
VECTOR_FLOOR = float(os.environ.get("VECTOR_FLOOR", "0.30"))  # tune by hand with sim/retrieval_eval.py
BM25_FLOOR = 0.5
STOP = set("a an the is are was to of and or in on for at by be can it i my me do does how what when we you your our with this that if not from as".split())


@dataclass
class Chunk:
    doc_id: str  # like "returns#return-window"
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


def load_chunks() -> list[Chunk]:
    chunks = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        doc = path.stem
        for section in re.split(r"\n(?=## )", path.read_text()):
            lines = section.strip().splitlines()
            if not lines or not lines[0].startswith("## "):
                continue
            heading = lines[0][3:].strip()
            body = " ".join(l.strip() for l in lines[1:] if l.strip())
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            chunks.append(Chunk(f"{doc}#{slug}", heading, f"{heading}. {body}"))
    return chunks


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            out.append(s)
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class PolicyIndex:
    def __init__(self, use_vectors: bool | None = None):
        self.chunks = load_chunks()
        self.bm25 = BM25([tokenize(c.text) for c in self.chunks])
        if use_vectors is None:
            use_vectors = bool(os.environ.get("OPENAI_API_KEY"))
        self.vectors: list[list[float]] | None = self._load_vectors() if use_vectors else None

    # ---- embeddings, cached by content hash ----
    def _fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([c.text for c in self.chunks]).encode()).hexdigest()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        resp = OpenAI().embeddings.create(model=EMBED_MODEL, input=texts)
        return [d.embedding for d in resp.data]

    def _load_vectors(self) -> list[list[float]] | None:
        fp = self._fingerprint()
        try:
            if POLICY_INDEX.exists():
                cached = json.loads(POLICY_INDEX.read_text())
                if cached.get("fingerprint") == fp and cached.get("model") == EMBED_MODEL:
                    return cached["vectors"]
            vectors = self._embed([c.text for c in self.chunks])
            POLICY_INDEX.write_text(json.dumps({"fingerprint": fp, "model": EMBED_MODEL, "vectors": vectors}))
            return vectors
        except Exception as e:  # no network or bad key: BM25 still works
            print(f"[search] embeddings unavailable, using BM25 only: {e}", flush=True)
            return None

    # ---- search ----
    def rank_bm25(self, query: str) -> list[tuple[int, float]]:
        s = self.bm25.scores(tokenize(query))
        return sorted(((i, v) for i, v in enumerate(s) if v > 0), key=lambda x: -x[1])

    def rank_vector(self, query: str) -> list[tuple[int, float]]:
        if not self.vectors:
            return []
        q = self._embed([query])[0]
        s = [_cosine(q, v) for v in self.vectors]
        return sorted(enumerate(s), key=lambda x: -x[1])

    def search(self, query: str, k: int = 3, mode: str = "hybrid") -> list[dict]:
        bm = self.rank_bm25(query) if mode in ("hybrid", "bm25") else []
        vec = self.rank_vector(query) if mode in ("hybrid", "vector") else []

        # Relevance floor: needs a real keyword hit, or a vector score over the floor.
        best_vec = vec[0][1] if vec else 0.0
        best_bm = bm[0][1] if bm else 0.0
        if best_vec < VECTOR_FLOOR and best_bm < BM25_FLOOR:
            return []

        # Reciprocal Rank Fusion: fuse by rank, not score, because the scales differ.
        fused: dict[int, float] = {}
        for ranking in (bm[:10], [x for x in vec[:10] if x[1] >= VECTOR_FLOOR * 0.8]):
            for rank, (i, _) in enumerate(ranking, 1):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{"doc_id": self.chunks[i].doc_id, "text": self.chunks[i].text} for i in top]


_INDEX: PolicyIndex | None = None


def get_index() -> PolicyIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = PolicyIndex()
    return _INDEX


def search_policy_text(query: str, k: int = 3) -> str:
    hits = get_index().search(query, k)
    if not hits:
        return "NO_RELEVANT_POLICY"
    return json.dumps(hits)
