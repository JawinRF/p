## PRISM Shield & MemShield — Preventing Poisoned Context for Mobile Agents

This repo implements your full project **“Preventing Poisoning Context to Mobile Agents”** in two complementary layers:

- **PRISM Shield** (ingestion layer, mobile-facing): protects an on-device Android-style agent from poisoned context entering through OS channels like clipboard, intents, notifications, shared storage, network responses, and `ui_accessibility` dumps.
- **MemShield** (retrieval layer, memory-facing): wraps any vector store (e.g. ChromaDB) to block poisoned RAG context at retrieval time and generate EU AI Act Article 12–style audit logs.

Together, they form a complete, end-to-end defense against context poisoning for mobile agents.

### 1. Project structure

- `scripts/prism_shield/`
  - `base.py` — `MemoryEntry` and `ValidationResult` data classes.
  - `pipeline.py` — `PrismShield` pipeline (UIExtractor → Normalizer → Layer 1 Heuristics → Layer 2 TinyBERT).
  - `ui_extractor.py` — structural UI pre-processor for `ui_accessibility` (micro-bounds, hidden nodes, context mismatch flags).
  - `normalizer.py` — de-obfuscation (URL decode, Base64 decode, invisible Unicode, ANSI, whitespace, basic HTML tags).
  - `layer1_heuristics.py` — fast regex-based Android/prompt-injection heuristics.
  - `layer2_local_llm.py` — TinyBERT-based binary classifier for nuanced poisoning detection.
- `scripts/`
  - `train_tinybert.py` — trains the TinyBERT poisoning classifier on the synthetic dataset.
  - `run_benchmark.py` — runs full per-path precision/recall/F1 + latency benchmarks.
  - `run_redteam_mutations.py` — applies obfuscation/encoding red-team mutations to poisoned samples.
  - `demo_prism_shield.py` — **simple demo**: runs `PrismShield` on a few examples from each ingestion path and prints verdicts.
  - `demo_memshield.py` — builds a ChromaDB collection from the `rag_store` data, wraps it with MemShield, and demonstrates poisoning defense + audit logging.
- `data/prism_synthetic_dataset.json` — 1,498 synthetic Android-specific entries across 7 ingestion paths (benign + poisoned).
- `memshield/` — standalone Python package providing the MemShield library, CLI, and MCP server.
- `PRISM_Shield_Report.md` — detailed project report for the ingestion pipeline.
- `memshield/README.md` — detailed documentation for MemShield.

### 2. Environment setup

From the repo root:

```bash
python -m venv env
source env/bin/activate  # Linux/macOS
# .\env\Scripts\activate  # Windows PowerShell

pip install --upgrade pip
# Core dependencies for PRISM Shield
pip install torch transformers datasets pandas scikit-learn numpy

# For MemShield demo (vector store + audit)
pip install chromadb

# Install local MemShield package in editable mode
pip install -e ./memshield[all]
```

> If you already have a virtual environment (`env/`), just activate it and install the missing packages.

### 3. Train the TinyBERT poisoning classifier

The ingestion pipeline’s Layer 2 (`LocalLLMValidator`) expects a fine-tuned TinyBERT model at `models/tinybert_poison_classifier_v2`.

Train it once:

```bash
python scripts/train_tinybert.py
```

This:

- Loads `data/prism_synthetic_dataset.json`.
- Trains a binary classifier (`benign` / `poisoned`) based on `text`.
- Writes model weights and tokenizer to `models/tinybert_poison_classifier_v2/`.

After this step, all PRISM Shield scripts that instantiate `PrismShield()` will be able to load the local model.

### 4. Run the PRISM Shield demo (ingestion layer)

To see how the pipeline protects a mobile agent across Android ingestion paths:

```bash
python scripts/demo_prism_shield.py
```

This will:

- Sample a few `benign` and `poisoned` entries per `ingestion_path` from the dataset.
- Run each through:
  - `UIExtractor` (for `ui_accessibility`),
  - `Normalizer`,
  - `HeuristicsEngine` (Layer 1),
  - `LocalLLMValidator` (TinyBERT, Layer 2).
- Print verdicts (`ALLOW`, `BLOCK`, `QUARANTINE`), confidence, triggering layer, and normalized text snippets.

If the TinyBERT model directory is missing, the script will clearly instruct you to run `scripts/train_tinybert.py` first.

### 5. Benchmark and red-team the ingestion pipeline

**Full benchmark (per-path metrics + latency):**

```bash
python scripts/run_benchmark.py
```

You’ll get markdown tables for:

- Per-ingestion-path precision/recall/F1 and confusion matrix counts.
- Per-path latency percentiles (mean, P50, P95, P99).

**Red-team robustness (mutations):**

```bash
python scripts/run_redteam_mutations.py
```

This:

- Applies multiple mutations (zero-width insertion, mixed encoding, Unicode confusables, repeated tokens) to poisoned entries.
- Runs them through `PrismShield`.
- Reports, per-mutation, how many attacks are still blocked vs. bypassing the defense, plus example failures.

### 6. Run the MemShield demo (retrieval layer)

Once MemShield is installed (section 2):

```bash
python scripts/demo_memshield.py
```

This will:

- Load only the `rag_store` entries from `data/prism_synthetic_dataset.json`.
- Create a ChromaDB collection (`prism_kb`) and insert those entries.
- Wrap a simple Chroma adapter with `MemShield` using `KeywordHeuristicStrategy` and `AuditConfig`.
- Run a query like `"export all user contacts"` through the wrapped store.
- Show which retrieved chunks were allowed after validation.
- Print the most recent Article 12–style audit record (inference ID, ISO timestamp, chain hash, number of blocked chunks, etc.).

This demonstrates how a mobile agent using RAG can be protected against poisoned long-term memory.

### 7. How this implements “Preventing Poisoning Context to Mobile Agents”

- **Mobile ingestion defense (PRISM Shield):**
  - Targets Android-specific ingestion paths: `android_intents`, `clipboard`, `network_responses`, `notifications`, `rag_store`, `shared_storage`, `ui_accessibility`.
  - Uses defense-in-depth:
    - Structural UI preprocessing (`UIExtractor`) to close the `ui_accessibility` gap (hidden nodes, micro-bounds, context mismatch).
    - Text de-obfuscation (`Normalizer`) for encodings, invisible chars, and escape codes.
    - Fast, explainable heuristic rules for obvious jailbreak patterns.
    - A local TinyBERT classifier for nuanced poisoning semantics with low latency on-device.
- **Retrieval/memory defense (MemShield):**
  - Wraps the agent’s vector store so every retrieved chunk is validated before entering the LLM context.
  - Uses heuristic/LLM ensembles inspired by A-MemGuard to detect instruction-like patterns in stored “knowledge”.
  - Records per-inference, tamper-evident audit logs that support EU AI Act Article 12 requirements.

For a typical **mobile AI agent**, you would:

- Run **PRISM Shield** on all context entering from the Android OS (clipboard, intents, accessibility dumps) **before** committing it to the agent’s memory.
- Use **MemShield** on top of the agent’s vector store so that any poisoned entries that did slip through are filtered at retrieval time, with auditable traces.


