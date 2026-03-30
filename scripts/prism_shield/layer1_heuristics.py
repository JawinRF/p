# scripts/prism_shield/layer1_heuristics.py

import re
from typing import Optional
from .base import ValidationResult

class HeuristicsEngine:
    def __init__(self):
        # High confidence block patterns
        self.block_patterns = [
            # Standard injection keywords
            r'(?i)\bignore (all )?previous (instructions|context|prompts)\b',
            r'(?i)\bsystem override\b',
            r'(?i)\byou must now act as\b',
            r'(?i)\bnew task:\b',
            
            # Action keywords
            r'(?i)\[AGENT( INSTRUCTION)?:.*?\]',
            r'(?i)\[AUTO-AGENT.*?\]',
            r'(?i)<system_override>',
            r'(?i)<hidden_instruction>',
            
            # UIExtractor structural flags
            r'\[HIDDEN_UI_ELEMENT\]',
            r'\[CONTEXT_MISMATCH.*?\]',
        ]
        
        # Medium confidence (quarantine/flag but maybe not immediate block unless combined)
        self.suspicious_patterns = [
            r'(?i)\bexport( all)? contacts\b',
            r'(?i)\bforward( all)? sms\b',
            r'(?i)\bsilently( approve| forward| delete)\b',
            r'(?i)\bant_permission\b',
            r'(?i)\badb shell pm grant\b',
            r'(?i)chmod 777'
        ]
        
        self._compiled_block = [re.compile(p) for p in self.block_patterns]
        self._compiled_suspicious = [re.compile(p) for p in self.suspicious_patterns]

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
