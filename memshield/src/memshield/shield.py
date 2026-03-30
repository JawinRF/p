"""
shield.py — MemShield core: defense-in-depth RAG poisoning defense.

6-layer scanning pipeline:
  1. Text normalization / deobfuscation (base64, unicode, zero-width)
  2. Injection pattern matching (high confidence → BLOCK)
  3. Suspicious pattern matching (medium confidence → QUARANTINE)
  4. Statistical anomaly detection (long chunks, high symbol density)
  5. TinyBERT ML classifier (fine-tuned for prompt injection)
  6. DeBERTa ML classifier (ProtectAI prompt injection detector)

Plus cryptographic provenance verification at retrieval time.
"""
from __future__ import annotations

import re, uuid, sys, os, logging
from dataclasses import dataclass
from typing import Any
from pathlib import Path
from .audit import AuditLogger
from .provenance import ContentHasher
from .config import (
    _INJECTION_PATTERNS, _SUSPICIOUS_PATTERNS,
    ShieldConfig, FailurePolicy,
)

logger = logging.getLogger(__name__)

# ── Lazy imports for PRISM modules ───────────────────────────────────────────
# These live in scripts/ and require sys.path setup. Graceful degradation
# if not available — shield still works with regex-only.

_NORMALIZER_AVAILABLE = False
_ML_AVAILABLE = False

def _ensure_scripts_path():
    """Add scripts/ to sys.path so prism_shield package is importable."""
    scripts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))),
        "scripts",
    )
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

try:
    _ensure_scripts_path()
    from prism_shield.normalizer import Normalizer as _Normalizer
    from prism_shield.base import MemoryEntry as _MemoryEntry
    _NORMALIZER_AVAILABLE = True
except ImportError:
    _Normalizer = None  # type: ignore[assignment,misc]
    _MemoryEntry = None  # type: ignore[assignment,misc]

try:
    _ensure_scripts_path()
    from prism_shield.layer2_local_llm import LocalLLMValidator as _LocalLLMValidator
    from prism_shield.layer3_deberta import DeBERTaValidator as _DeBERTaValidator
    _ML_AVAILABLE = True
except ImportError:
    _LocalLLMValidator = None  # type: ignore[assignment,misc]
    _DeBERTaValidator = None  # type: ignore[assignment,misc]


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ShieldResult:
    verdict: str        # ALLOW | BLOCK | QUARANTINE
    confidence: float
    reason: str
    chunk_id: str
    chunk_text: str
    pattern_matched: str | None = None
    layer_triggered: str | None = None


# ── Core shield ───────────────────────────────────────────────────────────────

class MemShield:
    """
    Defense-in-depth RAG poisoning scanner.

    Wraps a ChromaDB collection (optional) and provides multi-layer
    scanning: normalization → regex → statistical → ML → provenance.

    Failure policy: FAIL_CLOSED — on any error, block the chunk.
    """

    def __init__(
        self,
        collection=None,
        audit_log: str | Path = "data/memshield_audit.jsonl",
        fail_policy: str = "FAIL_CLOSED",
        quarantine_path: str | Path = "data/memshield_quarantine.jsonl",
        config: ShieldConfig | None = None,
        **kwargs,  # absorb legacy 'strategy' kwarg for backward compat
    ):
        self.collection    = collection
        self.config        = config or ShieldConfig()
        self.fail_policy   = fail_policy
        self.auditor       = AuditLogger(audit_log)
        self.quarantine    = Path(quarantine_path)
        self.quarantine.parent.mkdir(parents=True, exist_ok=True)

        # Normalization layer
        self._normalizer = None
        if self.config.enable_normalization:
            if _NORMALIZER_AVAILABLE:
                self._normalizer = _Normalizer()
                print("[MemShield] Normalization: ON (base64, unicode, zero-width deobfuscation)")
            else:
                raise ImportError(
                    "MemShield: enable_normalization=True but prism_shield.normalizer "
                    "not importable. Set enable_normalization=False to proceed without."
                )

        # ML layers
        self._tinybert = None
        self._deberta = None
        if self.config.enable_ml_layers:
            if not _ML_AVAILABLE:
                raise ImportError(
                    "MemShield: enable_ml_layers=True but prism_shield ML modules "
                    "not importable. Install torch/transformers or set enable_ml_layers=False."
                )
            self._tinybert = _LocalLLMValidator(self.config.ml_model_path)
            self._deberta = _DeBERTaValidator()
            print("[MemShield] ML Layers: ON (TinyBERT + DeBERTa)")
        elif self.config.enable_ml_layers is False:
            pass  # explicitly disabled, no warning needed

        if self.config.enable_provenance:
            print("[MemShield] Provenance: ON (SHA-256 content hash verification)")

    # ── Public API ────────────────────────────────────────────────────────────

    def query(
        self,
        query_texts: list[str],
        n_results: int = 5,
        session_id: str = "default",
        **kwargs,
    ) -> dict:
        """
        Drop-in replacement for collection.query().
        Poisoned chunks are removed from results and audit-logged.
        """
        try:
            raw = self.collection.query(
                query_texts=query_texts,
                n_results=n_results,
                **kwargs,
            )
        except Exception as exc:
            logger.error(f"ChromaDB query failed: {exc}")
            if self.fail_policy == "FAIL_CLOSED":
                return {"documents": [[]], "metadatas": [[]], "ids": [[]]}
            raise

        return self._filter_results(raw, session_id)

    def scan_chunk(self, text: str, chunk_id: str = "") -> ShieldResult:
        """Scan a single chunk through all enabled layers. Returns ShieldResult."""
        chunk_id = chunk_id or str(uuid.uuid4())[:8]

        # ── Layer 0: Normalization / deobfuscation ───────────────────────
        scan_text = text
        if self._normalizer and _MemoryEntry:
            try:
                entry = _MemoryEntry(id="", text=text, ingestion_path="rag_store")
                scan_text = self._normalizer.normalize(entry)
            except Exception as exc:
                logger.warning(f"Normalization failed: {exc}")
                return ShieldResult(
                    verdict="BLOCK",
                    confidence=0.90,
                    reason=f"Normalization failed (fail-closed): {exc}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    layer_triggered="Layer0-Normalization",
                )

        # ── Layer 1: Injection patterns (high confidence → BLOCK) ────────
        for pat in _INJECTION_PATTERNS:
            if pat.search(scan_text):
                return ShieldResult(
                    verdict="BLOCK",
                    confidence=0.97,
                    reason=f"Injection pattern matched: {pat.pattern[:60]}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    pattern_matched=pat.pattern,
                    layer_triggered="Layer1-Regex",
                )

        # ── Layer 2: Suspicious patterns (medium confidence → QUARANTINE)
        for pat in _SUSPICIOUS_PATTERNS:
            if pat.search(scan_text):
                return ShieldResult(
                    verdict="QUARANTINE",
                    confidence=0.72,
                    reason=f"Suspicious pattern matched: {pat.pattern[:60]}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    pattern_matched=pat.pattern,
                    layer_triggered="Layer2-Regex",
                )

        # ── Layer 3: Statistical anomaly ─────────────────────────────────
        if len(scan_text) > 2000:
            symbol_ratio = sum(
                1 for c in scan_text if not c.isalnum() and not c.isspace()
            ) / len(scan_text)
            if symbol_ratio > 0.35:
                return ShieldResult(
                    verdict="QUARANTINE",
                    confidence=0.65,
                    reason=f"Statistical anomaly: high symbol density ({symbol_ratio:.2f})",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    layer_triggered="Layer3-Stats",
                )

        # ── Layer 4: TinyBERT ML classifier ──────────────────────────────
        if self._tinybert:
            try:
                ml_result = self._tinybert.evaluate(scan_text, ingestion_path="rag_store")
                if ml_result.verdict != "ALLOW":
                    return ShieldResult(
                        verdict=ml_result.verdict,
                        confidence=ml_result.confidence,
                        reason=ml_result.reason,
                        chunk_id=chunk_id,
                        chunk_text=text,
                        layer_triggered="Layer4-TinyBERT",
                    )
            except Exception as exc:
                logger.warning(f"TinyBERT evaluation failed: {exc}")
                return ShieldResult(
                    verdict="BLOCK",
                    confidence=0.85,
                    reason=f"ML evaluation failed (fail-closed): {exc}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    layer_triggered="Layer4-TinyBERT",
                )

        # ── Layer 5: DeBERTa ML classifier ───────────────────────────────
        if self._deberta:
            try:
                ml_result = self._deberta.evaluate(scan_text, ingestion_path="rag_store")
                if ml_result.verdict != "ALLOW":
                    return ShieldResult(
                        verdict=ml_result.verdict,
                        confidence=ml_result.confidence,
                        reason=ml_result.reason,
                        chunk_id=chunk_id,
                        chunk_text=text,
                        layer_triggered="Layer5-DeBERTa",
                    )
            except Exception as exc:
                logger.warning(f"DeBERTa evaluation failed: {exc}")
                return ShieldResult(
                    verdict="BLOCK",
                    confidence=0.85,
                    reason=f"ML evaluation failed (fail-closed): {exc}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    layer_triggered="Layer5-DeBERTa",
                )

        # ── All layers passed ────────────────────────────────────────────
        return ShieldResult(
            verdict="ALLOW",
            confidence=0.95,
            reason="No injection patterns detected",
            chunk_id=chunk_id,
            chunk_text=text,
            layer_triggered="none",
        )

    def scan(self, chunks: list[str]) -> list[tuple[str, bool, str]]:
        """
        Scan a list of text chunks for poisoning.
        Returns: [(chunk_text, is_poisoned, reason), ...]
        """
        results = []
        for chunk in chunks:
            sr = self.scan_chunk(chunk)
            is_poisoned = sr.verdict != "ALLOW"
            results.append((chunk, is_poisoned, sr.reason))
        return results

    def validate_reads(self, documents: list[dict]) -> list[dict]:
        """
        Filter a list of document dicts, returning only those that pass scanning.
        Each document should have a 'content' key with the text to scan.
        """
        allowed = []
        for doc in documents:
            text = doc.get("content", "") if isinstance(doc, dict) else str(doc)
            sr = self.scan_chunk(text)
            if sr.verdict == "ALLOW":
                allowed.append(doc)
            else:
                logger.warning(f"validate_reads BLOCKED: {sr.reason}")
        return allowed

    def add_with_provenance(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
        **kwargs,
    ) -> None:
        """Add documents to ChromaDB with SHA-256 content hashes in metadata."""
        if self.collection is None:
            raise ValueError("No ChromaDB collection configured")
        if metadatas is None:
            metadatas = [{} for _ in documents]
        hashed_meta = [
            ContentHasher.hash_and_attach(doc, meta)
            for doc, meta in zip(documents, metadatas)
        ]
        self.collection.add(
            documents=documents,
            ids=ids,
            metadatas=hashed_meta,
            **kwargs,
        )

    # ── Internal ──────────────────────────────────────────────────────────

    def _filter_results(self, raw: dict, session_id: str) -> dict:
        """Remove blocked/quarantined chunks from ChromaDB results."""
        if not raw.get("documents"):
            return raw

        filtered_docs, filtered_meta, filtered_ids = [], [], []

        for batch_docs, batch_meta, batch_ids in zip(
            raw["documents"], raw["metadatas"], raw["ids"]
        ):
            clean_docs, clean_meta, clean_ids = [], [], []
            for doc, meta, cid in zip(batch_docs, batch_meta or [], batch_ids):

                # ── Provenance verification ──────────────────────────────
                if self.config.enable_provenance and not ContentHasher.verify(doc, meta):
                    result = ShieldResult(
                        verdict="BLOCK",
                        confidence=0.99,
                        reason="Provenance check failed: content hash mismatch "
                               "(possible post-ingestion tampering)",
                        chunk_id=cid,
                        chunk_text=doc,
                        layer_triggered="Provenance",
                    )
                else:
                    result = self.scan_chunk(doc, chunk_id=cid)

                self.auditor.log_retrieval(
                    verdict=result.verdict,
                    confidence=result.confidence,
                    reason=result.reason,
                    chunk_id=cid,
                    chunk_text=doc,
                    collection=getattr(self.collection, "name", "unknown"),
                    session_id=session_id,
                    metadata=meta or {},
                )

                if result.verdict == "ALLOW":
                    clean_docs.append(doc)
                    clean_meta.append(meta)
                    clean_ids.append(cid)
                elif result.verdict == "QUARANTINE":
                    self._quarantine_chunk(doc, cid, result)
                    logger.warning(f"QUARANTINED chunk {cid}: {result.reason}")
                else:
                    logger.warning(f"BLOCKED chunk {cid}: {result.reason}")

            filtered_docs.append(clean_docs)
            filtered_meta.append(clean_meta)
            filtered_ids.append(clean_ids)

        raw["documents"] = filtered_docs
        raw["metadatas"] = filtered_meta
        raw["ids"]       = filtered_ids
        return raw

    def _quarantine_chunk(self, text: str, chunk_id: str, result: ShieldResult) -> None:
        import json
        from datetime import datetime, timezone
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chunk_id": chunk_id,
            "verdict": result.verdict,
            "confidence": result.confidence,
            "reason": result.reason,
            "layer_triggered": result.layer_triggered,
            "text_preview": text[:200],
        }
        with self.quarantine.open("a") as f:
            f.write(json.dumps(record) + "\n")
