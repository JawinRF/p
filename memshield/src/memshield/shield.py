"""
shield.py — MemShield core: wraps ChromaDB to intercept and scan
retrieved RAG chunks for prompt injection before they reach the agent.
"""
from __future__ import annotations
import re, uuid, logging
from dataclasses import dataclass
from typing import Any
from pathlib import Path
from .audit import AuditLogger

logger = logging.getLogger(__name__)

# ── Heuristic patterns (same family as PRISM Layer 1) ────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(all\s+)?previous\s+(instructions|context|prompts)\b"),
    re.compile(r"(?i)\bforget\s+(everything|all|prior)\b"),
    re.compile(r"(?i)\bnew\s+(instruction|directive|task|objective)\b"),
    re.compile(r"(?i)\bsystem\s*:\s*override\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(a|an)\b"),
    re.compile(r"(?i)\bdo\s+not\s+(follow|obey|respect)\b"),
    re.compile(r"(?i)(exfil|send|upload|transfer).{0,40}(attacker|evil|malicious)"),
    re.compile(r"(?i)\b(jailbreak|dan\b|prompt\s*injection)\b"),
    re.compile(r"(?i)\[\s*(inject|override|system|admin)\s*\]"),
    re.compile(r"(?i)\bdisregard\s+(the\s+)?(previous|prior|original)\b"),
]

_SUSPICIOUS_PATTERNS = [
    re.compile(r"(?i)\bact\s+as\s+(if|though)\b"),
    re.compile(r"(?i)\bpretend\s+(you\s+are|to\s+be)\b"),
    re.compile(r"(?i)\bwithout\s+(restrictions|limits|filters)\b"),
    re.compile(r"(?i)\bin\s+developer\s+mode\b"),
]

# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ShieldResult:
    verdict: str        # ALLOW | BLOCK | QUARANTINE
    confidence: float
    reason: str
    chunk_id: str
    chunk_text: str
    pattern_matched: str | None = None


# ── Core shield ───────────────────────────────────────────────────────────────

class MemShield:
    """
    Wraps a ChromaDB collection. Call .query() instead of
    collection.query() — MemShield scans each retrieved chunk
    and blocks/quarantines poisoned results before they reach the agent.

    Failure policy: FAIL_CLOSED — on any error, block the chunk.
    """

    def __init__(
        self,
        collection,                          # chromadb Collection object
        audit_log: str | Path = "data/memshield_audit.jsonl",
        fail_policy: str = "FAIL_CLOSED",    # FAIL_CLOSED | FAIL_OPEN
        quarantine_path: str | Path = "data/memshield_quarantine.jsonl",
    ):
        self.collection    = collection
        self.fail_policy   = fail_policy
        self.auditor       = AuditLogger(audit_log)
        self.quarantine    = Path(quarantine_path)
        self.quarantine.parent.mkdir(parents=True, exist_ok=True)

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
        """Scan a single chunk. Returns ShieldResult with verdict."""
        chunk_id = chunk_id or str(uuid.uuid4())[:8]

        # Layer 1: injection patterns
        for pat in _INJECTION_PATTERNS:
            if pat.search(text):
                return ShieldResult(
                    verdict="BLOCK",
                    confidence=0.97,
                    reason=f"Injection pattern matched: {pat.pattern[:60]}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    pattern_matched=pat.pattern,
                )

        # Layer 2: suspicious patterns (lower confidence → QUARANTINE)
        for pat in _SUSPICIOUS_PATTERNS:
            if pat.search(text):
                return ShieldResult(
                    verdict="QUARANTINE",
                    confidence=0.72,
                    reason=f"Suspicious pattern matched: {pat.pattern[:60]}",
                    chunk_id=chunk_id,
                    chunk_text=text,
                    pattern_matched=pat.pattern,
                )

        # Layer 3: statistical anomaly (very long chunks, high symbol density)
        if len(text) > 2000:
            symbol_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / len(text)
            if symbol_ratio > 0.35:
                return ShieldResult(
                    verdict="QUARANTINE",
                    confidence=0.65,
                    reason=f"Statistical anomaly: high symbol density ({symbol_ratio:.2f})",
                    chunk_id=chunk_id,
                    chunk_text=text,
                )

        return ShieldResult(
            verdict="ALLOW",
            confidence=0.95,
            reason="No injection patterns detected",
            chunk_id=chunk_id,
            chunk_text=text,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

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
            "text_preview": text[:200],
        }
        with self.quarantine.open("a") as f:
            f.write(json.dumps(record) + "\n")
