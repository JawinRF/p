# scripts/prism_shield/pipeline.py
from __future__ import annotations

import threading
import time
import uuid

from openclaw_adapter.quarantine_store import (
    load_ticket,
    save_ticket,
    update_ticket,
    utc_now_iso,
)

from .base import FinalizedTicket, MemoryEntry, ValidationResult
from .normalizer import Normalizer
from .layer1_heuristics import HeuristicsEngine
from .layer2_local_llm import LocalLLMValidator
from .layer3_deberta import DeBERTaValidator
from .ui_extractor import UIExtractor
from .window_context_reader import start_reader
from .vlm_consistency_checker import vlm_checker
from .screen_context import NULL_CONTEXT, ScreenContext

class PrismShield:
    """
    Main entrypoint for evaluating incoming agent context.
    Executes UIExtractor (ui_accessibility only) -> Normalization -> Layer 1 (Heuristics) -> Layer 2 (Local LLM) 
    """
    def __init__(self):
        # Start the background Android WindowManager socket listener
        start_reader()
        # Initialize VLM in the background
        threading.Thread(target=vlm_checker.initialize, daemon=True).start()
        
        self.ui_extractor = UIExtractor()
        self.normalizer = Normalizer()
        self.heuristics = HeuristicsEngine()
        self.local_llm = LocalLLMValidator()
        self.deberta = DeBERTaValidator()

    def evaluate_sync(self, raw_entry: MemoryEntry) -> ValidationResult:
        # Step 0: UIExtractor pre-processing (ui_accessibility path only)
        if raw_entry.ingestion_path == "ui_accessibility":
            raw_entry.text = self.ui_extractor.extract(raw_entry.text)

        # Step 1: Normalize
        normalized_text = self.normalizer.normalize(raw_entry)

        # Step 2: Layer 1 Fast Path
        l1_result = self.heuristics.evaluate(normalized_text)
        if l1_result is not None:
            l1_result.normalized_text = normalized_text
            return l1_result

        # Step 3: Layer 2 Local Model Path
        # We only reach here if Layer 1 allowed it
        l2_result = self.local_llm.evaluate(normalized_text, raw_entry.ingestion_path)
        l2_result.normalized_text = normalized_text

        if l2_result.verdict == "QUARANTINE":
            ticket_id = str(uuid.uuid4())
            l2_result.ticket_id = ticket_id
            save_ticket(
                FinalizedTicket(
                    ticket_id=ticket_id,
                    status="PENDING",
                    confidence=l2_result.confidence,
                    reason=l2_result.reason,
                    layer_triggered=l2_result.layer_triggered,
                    created_at=utc_now_iso(),
                )
            )
            return l2_result

        # Step 4: Layer 3 DeBERTa — only when Layer 2 returned ALLOW
        if l2_result.verdict == "ALLOW":
            l3_result = self.deberta.evaluate(normalized_text, raw_entry.ingestion_path)
            l3_result.normalized_text = normalized_text
            if l3_result.verdict == "QUARANTINE":
                ticket_id = str(uuid.uuid4())
                l3_result.ticket_id = ticket_id
                save_ticket(
                    FinalizedTicket(
                        ticket_id=ticket_id,
                        status="PENDING",
                        confidence=l3_result.confidence,
                        reason=l3_result.reason,
                        layer_triggered=l3_result.layer_triggered,
                        created_at=utc_now_iso(),
                    )
                )
            if l3_result.verdict in ("BLOCK", "QUARANTINE"):
                return l3_result

        return l2_result

    def submit_quarantine(
        self,
        ticket_id: str,
        screenshot_path: str | None,
        screen_context: dict | ScreenContext | None,
    ) -> None:
        ticket = load_ticket(ticket_id)
        if ticket is None:
            raise KeyError(f"Unknown quarantine ticket: {ticket_id}")
        if ticket.status != "PENDING":
            return

        result = ValidationResult(
            verdict="QUARANTINE",
            confidence=ticket.confidence,
            reason=ticket.reason,
            layer_triggered=ticket.layer_triggered,
            ticket_id=ticket_id,
        )
        vlm_checker.check_async(result, self._coerce_screen_context(screen_context), screenshot_path)
        threading.Thread(
            target=self._watch_quarantine_resolution,
            args=(ticket_id, result),
            daemon=True,
            name=f"QuarantineWatcher-{ticket_id[:8]}",
        ).start()

    def get_ticket(self, ticket_id: str) -> FinalizedTicket | None:
        return load_ticket(ticket_id)

    def evaluate_entry(self, raw_entry: MemoryEntry) -> ValidationResult:
        result = self.evaluate_sync(raw_entry)
        if result.verdict != "QUARANTINE":
            return result

        screenshot_path = raw_entry.metadata.get("screenshot") if raw_entry.metadata else None
        if not screenshot_path and raw_entry.metadata:
            screenshot_path = raw_entry.metadata.get("screenshot_path")

        from .window_context_reader import get_current_context

        self.submit_quarantine(result.ticket_id, screenshot_path, get_current_context().to_dict())
        return result

    def _coerce_screen_context(self, screen_context: dict | ScreenContext | None) -> ScreenContext:
        if isinstance(screen_context, ScreenContext):
            return screen_context
        if isinstance(screen_context, dict):
            try:
                return ScreenContext.from_dict(screen_context)
            except Exception as exc:
                import logging
                logging.getLogger("PrismShield.Pipeline").warning(
                    f"ScreenContext parse failed (using NULL_CONTEXT): {exc}"
                )
                return NULL_CONTEXT
        return NULL_CONTEXT

    def _watch_quarantine_resolution(
        self,
        ticket_id: str,
        result: ValidationResult,
        timeout_s: float = 15.0,
        poll_interval_s: float = 0.1,
    ) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if result.verdict != "QUARANTINE":
                update_ticket(
                    ticket_id,
                    status=result.verdict,
                    confidence=result.confidence,
                    reason=result.reason,
                    layer_triggered=result.layer_triggered,
                )
                return
            time.sleep(poll_interval_s)

        update_ticket(
            ticket_id,
            status="BLOCK",
            confidence=1.0,
            reason="Quarantine timed out before VLM resolution",
            layer_triggered=result.layer_triggered,
        )
