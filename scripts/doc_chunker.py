"""
doc_chunker.py — Simple document chunking for RAG ingestion.
Splits text files into semantically meaningful chunks for ChromaDB storage.
"""
from __future__ import annotations

import os
from pathlib import Path


def chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into chunks by paragraphs, merging small ones and splitting large ones.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If paragraph alone exceeds max, split it
        if len(para) > max_chars:
            # Flush current buffer first
            if current:
                chunks.append(current.strip())
                current = ""
            # Split large paragraph with overlap
            for i in range(0, len(para), max_chars - overlap):
                piece = para[i : i + max_chars]
                if piece.strip():
                    chunks.append(piece.strip())
        elif len(current) + len(para) + 2 > max_chars:
            # Current buffer would overflow — flush it
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def load_and_chunk(filepath: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """
    Load a file and return chunks. Supports .txt, .md.
    PDF support requires PyPDF2 (optional).
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("PDF ingestion requires PyPDF2: pip install PyPDF2")
        reader = PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    return chunk_text(text, max_chars=max_chars, overlap=overlap)
