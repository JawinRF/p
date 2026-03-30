# scripts/generate_dataset.py

import json
import random
import argparse
from pathlib import Path

# Import generators
from generators.rag_generator import RAGGenerator
from generators.intent_generator import IntentGenerator
from generators.clipboard_generator import ClipboardGenerator
from generators.ui_generator import UIGenerator
from generators.notification_generator import NotificationGenerator
from generators.storage_generator import StorageGenerator
from generators.network_generator import NetworkGenerator

def main():
    parser = argparse.ArgumentParser(description="PRISM Dataset Generator")
    parser.add_argument("--output", type=str, default="data/prism_synthetic_dataset.json", help="Output file path")
    parser.add_argument("--samples", type=int, default=1500, help="Total number of samples to generate")
    args = parser.parse_args()

    print(f"Generating PRISM Synthetic Dataset (~{args.samples} samples)...")

    # Initialize all generators
    generators = [
        RAGGenerator(),
        IntentGenerator(),
        ClipboardGenerator(),
        UIGenerator(),
        NotificationGenerator(),
        StorageGenerator(),
        NetworkGenerator()
    ]
    
    # Calculate samples per generator
    samples_per_gen = args.samples // len(generators)
    
    all_samples = []
    
    for gen in generators:
        print(f"  -> Running {gen.__class__.__name__} ({samples_per_gen} samples)")
        samples = gen.generate(samples_per_gen)
        all_samples.extend(samples)
        
    print("Shuffling dataset...")
    random.shuffle(all_samples)
    
    # Calculate stats
    num_benign = sum(1 for s in all_samples if s["label"] == "benign")
    num_poisoned = sum(1 for s in all_samples if s["label"] == "poisoned")
    
    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_samples, f, indent=2, ensure_ascii=False)
        
    print(f"\nDone! Saved to {output_path}")
    print(f"Total samples: {len(all_samples)}")
    print(f"Benign: {num_benign} ({(num_benign/len(all_samples))*100:.1f}%)")
    print(f"Poisoned: {num_poisoned} ({(num_poisoned/len(all_samples))*100:.1f}%)")

if __name__ == "__main__":
    main()
