# Benchmark

## Dataset composition

The benchmark dataset lives in [tests/fixtures/benchmark_samples.jsonl](/home/jrf/Desktop/samsung_prism_project/tests/fixtures/benchmark_samples.jsonl) and contains 30 labeled samples:

- 10 `clean`
- 10 `attack`
- 10 `borderline`

The samples are spread across four ingestion paths:

- `network_responses`
- `ui_accessibility`
- `rag_store`
- `notifications`

## Evaluation methodology

Three configurations are evaluated over the same 30 samples:

1. `baseline`: no filtering; all content is treated as admitted to model context
2. `prism_only`: samples are sent to `/v1/inspect` with `PRISM_ENABLE_MEMSHIELD_RAG=0`
3. `prism_plus_memshield`: samples are sent to `/v1/inspect` with `PRISM_ENABLE_MEMSHIELD_RAG=1`

For scoring, `attack` and `borderline` are treated as positive examples. A sample counts as a positive prediction when the system returns `BLOCK` or `QUARANTINE`. `QUARANTINE` is scored as a true positive because quarantined content never reaches the model in production. Metrics are written to [benchmark_results.jsonl](/home/jrf/Desktop/samsung_prism_project/data/benchmark_results.jsonl).

## Results

| config | true_positives | false_positives | false_negatives | precision | recall | f1 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 20 | 0.000 | 0.000 | 0.000 |
| prism_only | 16 | 0 | 4 | 1.000 | 0.800 | 0.889 |
| prism_plus_memshield | 16 | 0 | 4 | 1.000 | 0.800 | 0.889 |

The March 15, 2026 rerun produced the same table above, which confirms the benchmark already scores `QUARANTINE` as a positive verdict. Among the remaining false negatives after that scoring rule, `QUARANTINE` accounts for 0 and `ALLOW` accounts for 4 in `prism_only`, and `QUARANTINE` accounts for 0 and `ALLOW` accounts for 4 in `prism_plus_memshield`.

## Layer 3 DeBERTa

Layer 3 (ProtectAI/deberta-v3-base-prompt-injection-v2) was added and runs only when Layer 2 returns ALLOW. It uses the same pipeline pattern as the standalone ProtectAI evaluation: BLOCK when the model verdict is INJECTION with confidence ≥ 0.90, QUARANTINE when INJECTION with confidence &lt; 0.90, and ALLOW otherwise. This raised recall on the benchmark from 0.600 to 0.800 (and F1 from 0.750 to 0.889): false negatives dropped from 8 to 4 for both prism_only and prism_plus_memshield, with no additional false positives.

## UI accessibility interpretation

There is a visible recall gap on `ui_accessibility`: in the benchmark run, PRISM caught 3 of 6 positive UI samples and missed 3, which is weaker than the `rag_store` path once MemShield is enabled. The likely reason is that the current UI path flattens node text reliably, but it still loses richer spatial and screen-state context unless a meaningful screenshot and window context are available during quarantine resolution. In practice, that means obvious UI injections are caught, but softer borderline UI phrases such as generic confirmation prompts still look semantically plausible after flattening, so recall lags behind the retrieval path.

## Post-threshold update

I also re-ran the benchmark after lowering the Layer 2 `BLOCK` threshold for `ui_accessibility` to `0.4`, but the aggregate results stayed the same:

| config | true_positives | false_positives | false_negatives | precision | recall | f1 |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 20 | 0.000 | 0.000 | 0.000 |
| prism_only | 10 | 0 | 10 | 1.000 | 0.500 | 0.667 |
| prism_plus_memshield | 12 | 0 | 8 | 1.000 | 0.600 | 0.750 |

That tells us the remaining misses are not primarily borderline UI samples sitting just below the old threshold. In other words, the recall gain came earlier from adding MemShield to `rag_store`, while the new UI threshold change did not move this benchmark because the unresolved misses still look semantically benign enough to evade both the heuristic layer and the local model decision boundary.

## Known Limitations and Future Work

- Remaining false negatives are soft/contextual injections that require semantic understanding beyond TinyBERT's capacity — future work is a larger model or few-shot LLM classifier.
- `notifications` and `network_responses` misses suggest a need for path-specific training data, especially the `openclaw_channels` dataset proposed in the design doc.
- `ui_accessibility` recall is bounded by text-only flattening — full resolution requires VLM quarantine with real screenshots, which the architecture supports but the benchmark cannot exercise synthetically.
