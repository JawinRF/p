# scripts/run_redteam_mutations.py

import json
import base64
import random
import urllib.parse
from prism_shield.base import MemoryEntry
from prism_shield.pipeline import PrismShield

# Maps ASCII characters to visually similar Unicode ('confusables')
CONFUSABLES = {
    'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
    'A': 'А', 'C': 'С', 'E': 'Е', 'O': 'О', 'P': 'Р', 'X': 'Х', 'Y': 'У',
    'i': 'і', 'j': 'ј', 's': 'ѕ', 'I': 'І', 'J': 'Ј', 'S': 'Ѕ',
}

def mutate_zero_width(text: str) -> str:
    """Inserts zero-width spaces (\u200B) pseudo-randomly."""
    return "".join(c + ("\u200B" if random.random() < 0.3 and c == " " else "") for c in text)

def mutate_mixed_encodings(text: str) -> str:
    """Base64 encodes the text, then URL encodes the result."""
    b64 = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return urllib.parse.quote(b64)

def mutate_unicode_confusables(text: str) -> str:
    """Swaps standard characters with homoglyphs."""
    return "".join(CONFUSABLES.get(c, c) for c in text)

def mutate_repeated_tokens(text: str, token: str = "SYSTEM:") -> str:
    """Repeats a key instruction token multiple times."""
    return text.replace(token, f"{token} {token} {token}")

def generate_mutations(dataset):
    print("Loading PRISM Shield Target for Red-Team Testing...")
    pipeline = PrismShield()
    
    # Filter for only poisoned entries
    poisoned_data = [d for d in dataset if d["label"] == "poisoned"]
    print(f"Applying mutations to {len(poisoned_data)} poisoned base payloads...")

    mutations = {
        "Zero-Width Insertion": mutate_zero_width,
        "Mixed Encoding (B64->URL)": mutate_mixed_encodings,
        "Unicode Confusables": mutate_unicode_confusables,
        "Repeated Tokens": mutate_repeated_tokens
    }

    results = {name: {"tested": 0, "blocked": 0, "bypassed": 0, "failures": []} for name in mutations}

    print("\n--- Running Red-Team Mutations ---")
    for item in poisoned_data:
        base_text = item["text"]
        path = item["ingestion_path"]
        
        for mut_name, mut_func in mutations.items():
            mutated_text = mut_func(base_text)
            
            # Create a mock entry with the mutated text
            entry = MemoryEntry(
                id=f"mut_{item['id']}",
                text=mutated_text,
                ingestion_path=path
            )
            
            result = pipeline.evaluate_entry(entry)
            
            # A poisoned entry should be BLOCKED or QUARANTINE.
            # If ALLOWED, it successfully bypassed the defense.
            results[mut_name]["tested"] += 1
            if result.verdict in ["BLOCK", "QUARANTINE"]:
                results[mut_name]["blocked"] += 1
            else:
                results[mut_name]["bypassed"] += 1
                # Log a few failures for debugging
                if len(results[mut_name]["failures"]) < 3:
                    results[mut_name]["failures"].append({
                        "path": path,
                        "original": base_text[:100] + "...",
                        "mutated": mutated_text[:100] + "...",
                        "confidence": result.confidence
                    })

    # Print Results
    for mut_name, stats in results.items():
        survived_pct = (stats['bypassed'] / stats['tested']) * 100
        print(f"\nMutation: {mut_name}")
        print(f"Tested: {stats['tested']} | Blocked: {stats['blocked']} | Bypassed: {stats['bypassed']} ({survived_pct:.1f}% Bypass Rate)")
        
        if stats['failures']:
            print("  Example Bypasses:")
            for fail in stats['failures']:
                print(f"    - [{fail['path']}] Allowed with Conf: {fail['confidence']:.2f}")

if __name__ == "__main__":
    import os
    base_dir = os.path.dirname(os.path.dirname(__file__))
    data_path = os.path.join(base_dir, "data/prism_synthetic_dataset.json")
    
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    generate_mutations(data)
