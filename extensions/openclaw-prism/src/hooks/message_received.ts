import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { inspect } from "../prism_client.js";
import { mapSource } from "../source_mapper.js";
import type { PluginConfig, PrismRequest } from "../types.js";

export function registerMessageReceivedHook(
  api: OpenClawPluginApi,
  config: PluginConfig,
): void {
  api.on("message_received", async (event, ctx) => {
    if (!config.protectSources.messages) {
      return;
    }

    const request: PrismRequest = {
      entry_id: `${ctx.channelId}:${String(event.timestamp ?? Date.now())}`,
      text: event.content,
      ingestion_path: mapSource("message_received", undefined, ctx.channelId),
      source_type: "message_received",
      source_name: ctx.channelId,
      session_id: ctx.conversationId ?? ctx.channelId,
      run_id: ctx.conversationId ?? ctx.channelId,
      metadata: {
        ...event.metadata,
        from: event.from,
        channelId: ctx.channelId,
        accountId: ctx.accountId,
        conversationId: ctx.conversationId,
      },
    };

    const result = await inspect(request, config);
    if (result.verdict !== "ALLOW") {
      api.logger.warn(
        `[openclaw-prism] observed inbound message flagged as ${result.verdict} on ${ctx.channelId}; enforcement occurs during context assembly`,
      );
    }
  });
}
