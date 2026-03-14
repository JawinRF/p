# OpenClaw Integration Notes

This repo now contains a first-pass OpenClaw integration scaffold:

- Python sidecar in [scripts/openclaw_adapter/server.py](./scripts/openclaw_adapter/server.py)
- OpenClaw plugin scaffold in [extensions/openclaw-prism/src/index.ts](./extensions/openclaw-prism/src/index.ts)

## What is implemented

- A stable, ticket-based PRISM API for quarantine handling
- A local HTTP sidecar with:
  - `POST /v1/inspect`
  - `GET /v1/ticket/{ticket_id}`
  - `GET /health`
- JSONL-backed persistence for quarantine tickets and audit records
- A conservative TypeScript plugin scaffold that calls the sidecar and enforces fail-closed behavior

## MemShield import path

The sidecar loads the vendored MemShield package from:

- `memshield/src/memshield/__init__.py`

The exact runtime import used in [server.py](/home/jrf/Desktop/samsung_prism_project/scripts/openclaw_adapter/server.py) is:

```python
from memshield import FailurePolicy, KeywordHeuristicStrategy, MemShield, ShieldConfig
```

To make that import resolve from this repo layout, the sidecar adds `memshield/src` to `sys.path` before importing.

## Real OpenClaw API alignment

I validated the scaffold against a local checkout of OpenClaw source:

- version: `2026.3.14`
- commit: `c083172`

Important runtime findings from the real plugin API:

- `registerContextEngine(...)` is real and is the correct enforcement anchor.
- `before_tool_call` can block or rewrite params and is the right pre-tool guard.
- `message_received` and `after_tool_call` are fire-and-forget hooks; they are useful for telemetry but not authoritative blocking.
- `tool_result_persist` and `before_message_write` are synchronous transcript-write hooks, so they cannot depend on an async HTTP sidecar call.
- `contextEngine.assemble(...)`, not `contextEngine.ingest(...)`, is the authoritative gate for what reaches the model prompt.

## What is intentionally still a scaffold

The TypeScript plugin does not claim to be fully wired against a checked-out OpenClaw source tree yet.
It is now written against the real plugin concepts and signatures:

- context engine
- `before_tool_call`
- `message_received`
- `after_tool_call`

The remaining gap is end-to-end runtime verification inside an actual OpenClaw workspace.

## Sidecar startup

From the repo root:

```bash
source env/bin/activate
python scripts/openclaw_adapter/server.py
```

The sidecar binds to `127.0.0.1:8765` only.

If `fastapi` is installed, the sidecar uses FastAPI + Uvicorn.
If not, it falls back to a stdlib JSON server exposing the same routes.

Optional shared-secret hardening:

```bash
export PRISM_SIDECAR_SECRET="change-me"
python scripts/openclaw_adapter/server.py
```

Then send `X-PRISM-Secret: change-me` from the plugin.

## Manual OpenClaw smoke test

This smoke test was validated against a local OpenClaw source checkout on this machine.

### 1. Start the PRISM sidecar

From this repo root:

```bash
source env/bin/activate
python scripts/openclaw_adapter/server.py
```

Expected result:

- the process stays up
- `curl http://127.0.0.1:8765/health` returns `{"status":"ok"}`

### 2. Install dependencies in the OpenClaw repo

From the OpenClaw checkout root:

```bash
pnpm install
```

### 3. Install and enable this plugin in OpenClaw

From the OpenClaw checkout root:

```bash
pnpm run openclaw -- plugins install /home/jrf/Desktop/samsung_prism_project/extensions/openclaw-prism
pnpm run openclaw -- plugins enable openclaw-prism
```

Expected result:

- `pnpm run openclaw -- plugins list` shows `openclaw-prism`
- `pnpm run openclaw -- plugins info openclaw-prism` resolves without a manifest/schema error
- the direct path form above works in a source checkout; the earlier `plugins install -l ...` form did not work against `2026.3.14`

### 4. Select the context engine slot

Set these values in the active OpenClaw config:

```toml
[gateway]
mode = "local"

[plugins.slots]
contextEngine = "prism-context"

[plugins.entries.openclaw-prism]
enabled = true

[plugins.entries.openclaw-prism.config]
sidecarUrl = "http://127.0.0.1:8765"
timeoutMs = 500
failClosed = true
quarantineMode = "exclude"
```

Observed runtime constraints from the real `2026.3.14` gateway:

- `gateway.mode = "local"` is required for this local loopback workflow, otherwise gateway startup is blocked
- plugin config must live under `plugins.entries.<id>.config`
- `plugins.config.<id>` is rejected as an unknown config key in this version

### 5. Start the OpenClaw gateway

From the OpenClaw checkout root:

```bash
pnpm run gateway:watch
```

Expected success signals:

- the gateway starts without a plugin manifest validation error
- there is no error like `Context engine "prism-context" is not registered`
- the plugin loads cleanly enough that `openclaw-prism` appears in the startup plugin set
- new runs hit the sidecar instead of silently falling back to the built-in `legacy` context engine

### 6. Optional plugin-local typecheck

If you only want to validate the extension package shape:

```bash
cd /home/jrf/Desktop/samsung_prism_project/extensions/openclaw-prism
pnpm install
pnpm run typecheck
```

That is useful for TypeScript sanity, but it is not a real runtime smoke test by itself.

## Current assumptions

- The Python side is implemented and locally runnable in this repo.
- The OpenClaw plugin side is aligned to the `2026.3.14` source snapshot and the plugin install/load/startup path was exercised against a live OpenClaw checkout.
- The plugin package now pins `openclaw` as a peer dependency at `2026.3.14`.

## Sync Hook Limitation

`tool_result_persist` and `before_message_write` are sync-only hooks in the real OpenClaw runtime.

That means they cannot safely call an async sidecar RPC before returning.

Because of that limitation, `contextEngine.assemble(...)` must be treated as the mandatory last line of defense before model assembly, not an optional extra layer.

## Milestone C Complete

The current stack now covers all three layers needed for the Milestone C story:

- ingestion-time defense through PRISM Shield in the `/v1/inspect` sidecar path
- retrieval-time defense through the `rag_store` MemShield branch in [server.py](/home/jrf/Desktop/samsung_prism_project/scripts/openclaw_adapter/server.py)
- pre-tool blocking through the OpenClaw `before_tool_call` hook in the plugin scaffold

In practical terms, that means untrusted inbound context can be filtered before prompt assembly, retrieved memory can be filtered before re-entry into future prompts, and risky tool execution can be blocked before the action runs.

## Suggested next step

Validate the sidecar end-to-end first, then clone or vendor the OpenClaw repo and align:

- plugin registration entrypoints
- message and tool-result object shapes
- memory integration points for MemShield

## Hook and gating limits

For the research claim, the honest boundary is:

- `message_received` and `after_tool_call` cannot mutate or replace content; they are telemetry-only.
- `before_tool_call` is the only async hook that can synchronously block or rewrite tool parameters before execution.
- `tool_result_persist` and `before_message_write` can synchronously rewrite or block transcript writes, but they are sync-only and therefore not suitable for an async sidecar RPC.
- inbound prompt safety is enforced in `contextEngine.assemble(...)`, which controls the final message list passed to the model.
- `contextEngine.ingest(...)` can affect what the engine stores, but by itself it is not the final prompt gate.
