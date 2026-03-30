"""
config.py — FailurePolicy, ShieldConfig, KeywordHeuristicStrategy
"""
from __future__ import annotations
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class FailurePolicy(Enum):
    BLOCK = "BLOCK"
    ALLOW = "ALLOW"

_INJECTION_PATTERNS = [
    # -- Original patterns --
    re.compile(r"(?i)\bignore\s+(all\s+)?previous\s+(instructions|context|prompts)\b"),
    re.compile(r"(?i)\bforget\s+(everything|all|prior)\b"),
    re.compile(r"(?i)\bnew\s+(instruction|directive|objective)\s*[:;]"),
    re.compile(r"(?i)\bsystem\s*:\s*override\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(a|an)\b"),
    re.compile(r"(?i)\bdo\s+not\s+(follow|obey|respect)\b"),
    re.compile(r"(?i)(exfil|send|upload|transfer).{0,40}(attacker|evil|malicious)"),
    re.compile(r"(?i)\b(jailbreak|dan\b|prompt\s*injection)\b"),
    re.compile(r"(?i)\[\s*(inject|override|system|admin)\s*\]"),
    re.compile(r"(?i)\bdisregard\s+(the\s+)?(previous|prior|original)\b"),
    # -- Additional patterns from PRISM Layer 1 heuristics --
    re.compile(r"(?i)\[AGENT\s*INSTRUCTION:.*?\]"),
    re.compile(r"(?i)\[AUTO-AGENT.*?\]"),
    re.compile(r"(?i)<system_override>"),
    re.compile(r"(?i)<hidden_instruction>"),
    re.compile(r"(?i)\byou\s+must\s+now\s+act\s+as\b"),
    re.compile(r"(?i)\bnew\s+task\s*:"),
    re.compile(r"(?i)\[HIDDEN_UI_ELEMENT\]"),
    re.compile(r"(?i)\[CONTEXT_MISMATCH.*?\]"),
]

_SUSPICIOUS_PATTERNS = [
    # -- Original patterns --
    re.compile(r"(?i)\bact\s+as\s+(if|though)\b"),
    re.compile(r"(?i)\bpretend\s+(you\s+are|to\s+be)\b"),
    re.compile(r"(?i)\bwithout\s+(restrictions|limits|filters)\b"),
    re.compile(r"(?i)\bin\s+developer\s+mode\b"),
    # -- Android device control / privilege escalation --
    re.compile(r"(?i)\bexport\s+(all\s+)?contacts\b"),
    re.compile(r"(?i)\bforward\s+(all\s+)?sms\b"),
    re.compile(r"(?i)\bsilently\s+(approve|forward|delete)\b"),
    re.compile(r"(?i)\badb\s+shell\s+pm\s+grant\b"),
    re.compile(r"(?i)chmod\s+777"),
]

@dataclass
class ShieldConfig:
    enabled: bool = True
    failure_policy: FailurePolicy = FailurePolicy.BLOCK
    confidence_threshold: float = 0.5
    enable_provenance: bool = False
    enable_normalization: bool = True
    enable_ml_layers: bool = False
    ml_model_path: str = "models/tinybert_poison_classifier_v2"
    extra: dict[str, Any] = field(default_factory=dict)

class KeywordHeuristicStrategy:
    """
    Heuristic strategy used by MemShield and the sidecar.
    Mirrors PRISM Layer 1 patterns for consistency.
    """
    def validate(self, text: str) -> dict:
        for pat in _INJECTION_PATTERNS:
            if pat.search(text):
                return {
                    "verdict": "BLOCK",
                    "confidence": 0.97,
                    "reason": f"Injection pattern: {pat.pattern[:60]}",
                    "pattern": pat.pattern,
                }
        for pat in _SUSPICIOUS_PATTERNS:
            if pat.search(text):
                return {
                    "verdict": "QUARANTINE",
                    "confidence": 0.72,
                    "reason": f"Suspicious pattern: {pat.pattern[:60]}",
                    "pattern": pat.pattern,
                }
        return {
            "verdict": "ALLOW",
            "confidence": 0.95,
            "reason": "No injection patterns detected",
            "pattern": None,
        }
