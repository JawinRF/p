# scripts/prism_shield/layer3_deberta.py
"""
Layer 3: DeBERTa-based prompt injection classifier (ProtectAI/deberta-v3-base-prompt-injection-v2).
Invoked only when Layer 2 returns ALLOW. Apache 2.0, no gating.
"""

from __future__ import annotations

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

from .base import ValidationResult


class DeBERTaValidator:
    """ProtectAI DeBERTa prompt-injection classifier. BLOCK/QUARANTINE on INJECTION by confidence."""

    MODEL_ID = "ProtectAI/deberta-v3-base-prompt-injection-v2"
    BLOCK_THRESHOLD = 0.90  # INJECTION with confidence >= this -> BLOCK
    # INJECTION with confidence < BLOCK_THRESHOLD -> QUARANTINE

    def __init__(self) -> None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
        model = AutoModelForSequenceClassification.from_pretrained(self.MODEL_ID)
        self._classifier = pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            truncation=True,
            max_length=512,
            device=device,
        )

    def evaluate(self, normalized_text: str, ingestion_path: str = "") -> ValidationResult:
        out = self._classifier(normalized_text)[0]
        verdict_label = out["label"]
        confidence = out["score"]

        is_injection = verdict_label.upper() == "INJECTION"

        if is_injection and confidence >= self.BLOCK_THRESHOLD:
            return ValidationResult(
                verdict="BLOCK",
                confidence=confidence,
                reason="Layer 3 DeBERTa identified prompt injection",
                layer_triggered="Layer3-DeBERTa",
            )
        if is_injection and confidence < self.BLOCK_THRESHOLD:
            return ValidationResult(
                verdict="QUARANTINE",
                confidence=confidence,
                reason="Layer 3 DeBERTa detected possible injection; confidence below block threshold",
                layer_triggered="Layer3-DeBERTa",
            )
        return ValidationResult(
            verdict="ALLOW",
            confidence=1.0 - confidence,
            reason="Layer 3 DeBERTa deemed safe",
            layer_triggered="Layer3-DeBERTa",
        )
