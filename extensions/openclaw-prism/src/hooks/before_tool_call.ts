import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { inspect } from "../prism_client.js";
import { mapSource } from "../source_mapper.js";
import type { PluginConfig, PrismRequest } from "../types.js";

function stringifyParams(params: Record<string, unknown>): string {
  try {
    return JSON.stringify(params);
  } catch {
    return "";
  }
}

export function registerBeforeToolCallHook(
  api: OpenClawPluginApi,
  config: PluginConfig,
): void {
  api.on("before_tool_call", async (event, ctx) => {
    const text = stringifyParams(event.params);
    if (!text) {
      return;
    }

    const request: PrismRequest = {
      entry_id: `${ctx.runId ?? "run"}:${event.toolCallId ?? event.toolName}:before`,
      text,
      ingestion_path: mapSource("before_tool_call", event.toolName, event.toolName),
      source_type: "before_tool_call",
      source_name: event.toolName,
      session_id: ctx.sessionId ?? ctx.sessionKey ?? "unknown",
      run_id: ctx.runId ?? ctx.sessionId ?? "unknown",
      metadata: {
        toolName: event.toolName,
        params: event.params,
      },
    };

    const result = await inspect(request, config);
    if (result.verdict === "BLOCK" || result.verdict === "QUARANTINE") {
      return {
        block: true,
        blockReason: `PRISM blocked ${event.toolName}: ${result.reason}`,
      };
    }

    return undefined;
  });
}
