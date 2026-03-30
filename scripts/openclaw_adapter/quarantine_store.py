from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from prism_shield.base import FinalizedTicket


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = PROJECT_ROOT / "data" / "quarantine_store.jsonl"


def _ensure_store() -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.touch(exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_ticket(ticket: FinalizedTicket) -> None:
    _ensure_store()
    with STORE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(ticket), ensure_ascii=True) + "\n")


def load_ticket(ticket_id: str) -> FinalizedTicket | None:
    _ensure_store()
    latest: dict | None = None
    with STORE_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("ticket_id") == ticket_id:
                latest = record

    if latest is None:
        return None

    return FinalizedTicket(
        ticket_id=latest["ticket_id"],
        status=latest["status"],
        confidence=float(latest["confidence"]),
        reason=latest["reason"],
        layer_triggered=latest.get("layer_triggered", "Layer2-LocalLLM"),
        created_at=latest.get("created_at", utc_now_iso()),
        resolved_at=latest.get("resolved_at"),
    )


def update_ticket(
    ticket_id: str,
    status: str,
    confidence: float,
    reason: str,
    layer_triggered: str | None = None,
) -> FinalizedTicket:
    current = load_ticket(ticket_id)
    if current is None:
        raise KeyError(f"Unknown quarantine ticket: {ticket_id}")

    ticket = FinalizedTicket(
        ticket_id=ticket_id,
        status=status,
        confidence=confidence,
        reason=reason,
        layer_triggered=layer_triggered or current.layer_triggered,
        created_at=current.created_at,
        resolved_at=None if status == "PENDING" else utc_now_iso(),
    )
    save_ticket(ticket)
    return ticket

