import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { inspect } from "../prism_client.js";
import { mapSource } from "../source_mapper.js";
import type { PluginConfig, PrismRequest } from "../types.js";

function stringifyResult(result: unknown): string {
  if (typeof result === "string") {
    return result;
  }
  try {
    return JSON.stringify(result);
  } catch {
    return "";
  }
}

export function registerAfterToolCallHook(
  api: OpenClawPluginApi,
  config: PluginConfig,
): void {
  api.on("after_tool_call", async (event, ctx) => {
    if (!config.protectSources.toolResults) {
      return;
    }

    const text = stringifyResult(event.result);
    if (!text) {
      return;
    }

    const request: PrismRequest = {
      entry_id: `${ctx.runId ?? "run"}:${event.toolCallId ?? event.toolName}`,
      text,
      ingestion_path: mapSource("after_tool_call", event.toolName, event.toolName),
      source_type: "after_tool_call",
      source_name: event.toolName,
      session_id: ctx.sessionId ?? ctx.sessionKey ?? "unknown",
      run_id: ctx.runId ?? ctx.sessionId ?? "unknown",
      metadata: {
        toolName: event.toolName,
        durationMs: event.durationMs,
      },
    };

    const result = await inspect(request, config);
    if (result.verdict !== "ALLOW") {
      api.logger.warn(
        `[openclaw-prism] tool output from ${event.toolName} flagged as ${result.verdict}; authoritative filtering occurs during persistence/assembly`,
      );
    }
  });
}
