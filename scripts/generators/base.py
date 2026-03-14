# scripts/generators/base.py
from abc import ABC, abstractmethod
import random
import uuid
import uuid


class BaseGenerator(ABC):
    def __init__(self, ingestion_path: str):
        self.ingestion_path = ingestion_path
        self.target_actions = [
            "pii_exfiltration", "permission_escalation", 
            "unauthorized_transaction", "delete_data", 
            "modify_settings", "phishing_redirect"
        ]
        self.attack_types = [
            "instruction_injection", "role_override", 
            "context_flooding", "obfuscated_payload",
            "encoded_payload"
        ]
        self.severities = ["low", "medium", "high", "critical"]

    def _generate_id(self, prefix: str = "") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def _distribute_samples(self, num_samples: int, poison_ratio: float = 0.4) -> tuple[int, int]:
        num_poisoned = int(num_samples * poison_ratio)
        num_benign = num_samples - num_poisoned
        return num_benign, num_poisoned

    @abstractmethod
    def generate_benign(self, num_samples: int) -> list[dict]:
        """Generate benign samples."""
        pass

    @abstractmethod
    def generate_poisoned(self, num_samples: int) -> list[dict]:
        """Generate poisoned samples."""
        pass

    def generate(self, num_samples: int) -> list[dict]:
        num_benign, num_poisoned = self._distribute_samples(num_samples)
        
        benign_samples = self.generate_benign(num_benign)
        poisoned_samples = self.generate_poisoned(num_poisoned)
        
        dataset = benign_samples + poisoned_samples
        random.shuffle(dataset)
        return dataset
