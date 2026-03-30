# scripts/prism_shield/layer1_heuristics.py

import sys
import os
from typing import Optional
from .base import ValidationResult

# Import from single source of truth
_scripts_dir = os.path.dirname(os.path.dirname(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from shared_patterns import INJECTION_PATTERNS, SUSPICIOUS_PATTERNS


class HeuristicsEngine:
    def __init__(self):
        # Patterns are pre-compiled in shared_patterns.py
        self._compiled_block = INJECTION_PATTERNS
        self._compiled_suspicious = SUSPICIOUS_PATTERNS

    def evaluate(self, normalized_text: str) -> Optional[ValidationResult]:
        """
        Returns a ValidationResult if a heuristic triggers, otherwise None (pass to Layer 2).
        """
        # Fast fail for explicit override strings
        for pattern in self._compiled_block:
            if pattern.search(normalized_text):
                return ValidationResult(
                    verdict="BLOCK",
                    confidence=0.99,
                    reason=f"Layer 1 Heuristic matched exact jailbreak/override pattern: {pattern.pattern}",
                    layer_triggered="Layer1-Heuristics"
                )
                
        # Count suspicious Android-specific operations
        suspicious_hits = 0
        for pattern in self._compiled_suspicious:
            if pattern.search(normalized_text):
                suspicious_hits += 1
                
        if suspicious_hits >= 2:
            return ValidationResult(
                verdict="BLOCK",
                confidence=0.85,
                reason="Layer 1 Heuristic matched multiple dangerous Android API combinations.",
                layer_triggered="Layer1-Heuristics"
            )
        elif suspicious_hits == 1:
            # We don't block on just one suspicious word, defer to Local LLM to understand context
            pass
            
        return None  # Clean according to Layer 1, proceed to Layer 2
