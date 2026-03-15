"""
audit.py — EU AI Act Article 12 compliant audit logging for MemShield.
"""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class AuditRecord:
    timestamp: str
    event: str           # "retrieval_allowed" | "retrieval_blocked" | "quarantined"
    verdict: str
    confidence: float
    reason: str
    chunk_id: str
    chunk_preview: str   # first 120 chars only
    collection: str
    session_id: str
    metadata: dict[str, Any]

class AuditLogger:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: AuditRecord) -> None:
        with self.log_path.open("a") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def log_retrieval(
        self,
        verdict: str,
        confidence: float,
        reason: str,
        chunk_id: str,
        chunk_text: str,
        collection: str,
        session_id: str = "default",
        metadata: dict | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=f"retrieval_{'blocked' if verdict in ('BLOCK','QUARANTINE') else 'allowed'}",
            verdict=verdict,
            confidence=confidence,
            reason=reason,
            chunk_id=chunk_id,
            chunk_preview=chunk_text[:120],
            collection=collection,
            session_id=session_id,
            metadata=metadata or {},
        )
        self.log(record)
        return record

    def tail(self, n: int = 10) -> list[AuditRecord]:
        try:
            lines = self.log_path.read_text().strip().split("\n")
            return [AuditRecord(**json.loads(l)) for l in lines[-n:] if l]
        except FileNotFoundError:
            return []
