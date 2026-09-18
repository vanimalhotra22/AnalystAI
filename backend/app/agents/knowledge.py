"""Policy knowledge base (the RAG component).

Business policy lives in documents, not in the warehouse, so the recommendation
step retrieves the relevant policy clause and cites it instead of inventing a
number like "increase safety stock by 15%".

Retrieval is TF-IDF over heading-level chunks: dependency-free, deterministic
and offline, which matters for a demo.  Swapping in sentence embeddings + FAISS
is a drop-in change behind `search()` -- the corpus is a few dozen chunks, so it
would buy recall on paraphrases, not speed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import ROOT

POLICY_DIR = ROOT / "docs" / "policies"


@dataclass
class Chunk:
    doc: str
    title: str
    section: str
    text: str


def _split(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    title = raw.splitlines()[0].lstrip("# ").strip()
    parts = re.split(r"\n(?=## )", raw)
    chunks = []
    for part in parts:
        head = part.splitlines()[0].strip()
        section = head.lstrip("# ").strip()
        body = part.strip()
        if len(body) < 40:
            continue
        chunks.append(Chunk(doc=path.name, title=title, section=section, text=body))
    return chunks


@lru_cache(maxsize=1)
def _index():
    chunks: list[Chunk] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        chunks.extend(_split(path))
    corpus = [f"{c.title} {c.section} {c.text}" for c in chunks]
    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
    matrix = vec.fit_transform(corpus) if corpus else None
    return chunks, vec, matrix


def search(query: str, k: int = 3, min_score: float = 0.04) -> list[dict]:
    chunks, vec, matrix = _index()
    if matrix is None or not query.strip():
        return []
    sims = cosine_similarity(vec.transform([query]), matrix)[0]
    order = sims.argsort()[::-1][:k]
    out = []
    for i in order:
        if sims[i] < min_score:
            continue
        c = chunks[i]
        out.append({
            "document": c.doc, "policy": c.title, "section": c.section,
            "relevance": round(float(sims[i]), 3),
            "excerpt": _trim(c.text),
        })
    return out


def _trim(text: str, max_chars: int = 700) -> str:
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars].rsplit("\n", 1)[0] + "\n..."


def corpus_summary() -> dict:
    chunks, _, _ = _index()
    docs = sorted({c.doc for c in chunks})
    return {"documents": docs, "chunks": len(chunks), "directory": str(POLICY_DIR)}
