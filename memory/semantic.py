"""Local vectorisation utilities for semantic memory retrieval.

The default embedder is intentionally lightweight so the quickstart can run
without an external vector database or embedding API during local testing.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod


_ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


class BaseEmbedder(ABC):
    """Embeds text into a dense vector."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert input text into a vector."""
        ...


class HashingEmbedder(BaseEmbedder):
    """Deterministic local embedder based on token hashing.

    This is a pragmatic fallback for local development and tests. The API is
    intentionally compatible with a future real embedding service.
    """

    def __init__(self, dimensions: int = 256):
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        tokens = tokenize_text(text)
        if not tokens:
            return [0.0] * self._dimensions

        vector = [0.0] * self._dimensions
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self._dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def tokenize_text(text: str) -> list[str]:
    """Tokenize Latin words and Chinese character bigrams for mixed-language text."""

    normalized = text.lower().strip()
    if not normalized:
        return []

    tokens = _ASCII_TOKEN_RE.findall(normalized)
    cjk_chars = _CJK_CHAR_RE.findall(normalized)
    tokens.extend(cjk_chars)
    tokens.extend(
        f"{cjk_chars[i]}{cjk_chars[i + 1]}" for i in range(len(cjk_chars) - 1)
    )
    return tokens


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for already dense vectors."""

    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
