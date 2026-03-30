"""
provenance.py — Cryptographic content hashing for RAG chunk integrity.

Implements the data provenance layer recommended by defense-in-depth
research (simplified Merkle tree). SHA-256 hashes are stored in ChromaDB
metadata at ingestion time and verified at retrieval time to detect
post-ingestion tampering.
"""
from __future__ import annotations

import hashlib


class ContentHasher:
    """SHA-256 content hashing for RAG chunk provenance."""

    HASH_KEY = "content_hash"

    @staticmethod
    def hash_chunk(text: str) -> str:
        """Return hex SHA-256 of the UTF-8 encoded text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def hash_and_attach(cls, text: str, metadata: dict | None = None) -> dict:
        """Compute hash and store it in metadata. Returns updated metadata."""
        meta = dict(metadata) if metadata else {}
        meta[cls.HASH_KEY] = cls.hash_chunk(text)
        return meta

    @classmethod
    def verify(cls, text: str, metadata: dict | None) -> bool:
        """
        Return True if metadata hash matches current hash of text.
        Returns True if no hash present (backward compatible with
        pre-provenance data).
        """
        if not metadata or cls.HASH_KEY not in metadata:
            return True  # no provenance data — allow legacy chunks
        return metadata[cls.HASH_KEY] == cls.hash_chunk(text)
