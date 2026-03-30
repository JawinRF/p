"""
One-off: Run the 8 prism_plus_memshield false-negative samples through v1
(tinybert_poison_classifier) using the same logic as predict_prompt.py.
Reports: entry_id, ingestion_path, v1 verdict, v1 confidence.
Makes no changes to the codebase; run from project root with:
  PYTHONPATH=scripts env/bin/python scripts/benchmark/report_fn_v1.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "tests" / "fixtures" / "benchmark_samples.jsonl"
RESULTS_PATH = PROJECT_ROOT / "data" / "benchmark_results.jsonl"
PYTHON_BIN = PROJECT_ROOT / "env" / "bin" / "python"
SIDECAR_SCRIPT = PROJECT_ROOT / "scripts" / "openclaw_adapter" / "server.py"
PYTHONPATH_VALUE = str(PROJECT_ROOT / "scripts")
V1_MODEL_PATH = PROJECT_ROOT / "models" / "tinybert_poison_classifier"


def load_dataset() -> list[dict]:
    with DATASET_PATH.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def is_positive(sample: dict) -> bool:
    return sample["label"] in {"attack", "borderline"}


def predicted_positive(verdict: str) -> bool:
    return verdict in {"BLOCK", "QUARANTINE"}


def run_sidecar(port: int, enable_memshield_rag: bool) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH_VALUE
    env["PRISM_SIDECAR_HOST"] = "127.0.0.1"
    env["PRISM_SIDECAR_PORT"] = str(port)
    env["PRISM_ENABLE_MEMSHIELD_RAG"] = "1" if enable_memshield_rag else "0"

    proc = subprocess.Popen(
        [str(PYTHON_BIN), str(SIDECAR_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + 30
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            raise RuntimeError(f"Sidecar exited early.\nstdout:\n{stdout}\nstderr:\n{stderr}")
        try:
            response = requests.get(url, timeout=0.5)
            if response.status_code == 200:
                return proc
        except requests.RequestException:
            time.sleep(0.2)

    proc.kill()
    stdout, stderr = proc.communicate(timeout=1)
    raise RuntimeError(f"Sidecar health check timed out.\nstdout:\n{stdout}\nstderr:\n{stderr}")


def stop_sidecar(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def inspect_sample(base_url: str, sample: dict) -> dict:
    payload = {
        "entry_id": sample["entry_id"],
        "text": sample["text"],
        "ingestion_path": sample["ingestion_path"],
        "source_type": sample["source_type"],
        "source_name": sample["source_name"],
        "session_id": f"bench-{sample['entry_id']}",
        "run_id": f"bench-{sample['entry_id']}",
        "metadata": sample.get("metadata", {}),
    }
    response = requests.post(f"{base_url}/v1/inspect", json=payload, timeout=10)
    response.raise_for_status()
    data = response.json()
    data["entry_id"] = sample["entry_id"]
    data["ingestion_path"] = sample["ingestion_path"]
    data["label"] = sample["label"]
    data["text"] = sample["text"]
    return data


def get_prism_plus_memshield_false_negatives() -> list[dict]:
    dataset = load_dataset()
    proc = run_sidecar(8891, enable_memshield_rag=True)
    try:
        base_url = "http://127.0.0.1:8891"
        rows = [inspect_sample(base_url, s) for s in dataset]
    finally:
        stop_sidecar(proc)

    fn_samples = []
    for row in rows:
        if is_positive(row) and not predicted_positive(row["verdict"]):
            fn_samples.append({
                "entry_id": row["entry_id"],
                "ingestion_path": row["ingestion_path"],
                "label": row["label"],
                "text": row["text"],
            })
    return fn_samples


def v1_predict(text: str, tokenizer, model, device: str) -> tuple[str, float]:
    """Same logic as predict_prompt.py: tokenize, forward, argmax, softmax."""
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128,
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    pred = torch.argmax(logits, dim=1).item()
    confidence = torch.softmax(logits, dim=1)[0][pred].item()

    if pred == 1:
        verdict = "POISONED"
    else:
        verdict = "BENIGN"

    return verdict, confidence


def main() -> int:
    if not V1_MODEL_PATH.exists():
        print(f"V1 model not found: {V1_MODEL_PATH}", file=sys.stderr)
        return 1

    print("Identifying prism_plus_memshield false negatives...")
    fn_samples = get_prism_plus_memshield_false_negatives()
    if len(fn_samples) != 8:
        print(f"Expected 8 FN, got {len(fn_samples)}", file=sys.stderr)
        return 1

    print(f"Loaded V1 model from {V1_MODEL_PATH}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(str(V1_MODEL_PATH))
    model = AutoModelForSequenceClassification.from_pretrained(str(V1_MODEL_PATH))
    model.to(device)
    model.eval()

    print("\n--- V1 (tinybert_poison_classifier) on 8 prism_plus_memshield false negatives ---\n")
    print("entry_id                 | ingestion_path    | v1_verdict | v1_confidence")
    print("-" * 75)

    for sample in fn_samples:
        verdict, confidence = v1_predict(sample["text"], tokenizer, model, device)
        print(f"{sample['entry_id']:24} | {sample['ingestion_path']:17} | {verdict:10} | {confidence:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
