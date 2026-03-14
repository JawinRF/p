import type { AgentMessage } from "@mariozechner/pi-agent-core";
import type { AssembleResult, CompactResult, ContextEngine, IngestResult } from "openclaw/plugin-sdk/core";
import { inspect } from "./prism_client.js";
import { isTrusted, mapSource } from "./source_mapper.js";
import type { PluginConfig, PrismRequest, PrismResponse } from "./types.js";

type LoggerLike = {
  warn: (message: string) => void;
  info?: (message: string) => void;
};

function extractTextFromValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (!item || typeof item !== "object") {
          return "";
        }
        const record = item as Record<string, unknown>;
        if (typeof record.text === "string") {
          return record.text;
        }
        if (typeof record.content === "string") {
          return record.content;
        }
        if (typeof record.name === "string") {
          return record.name;
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "";
    }
  }
  return "";
}

function getMessageText(message: AgentMessage): string {
  const record = message as Record<string, unknown>;
  return extractTextFromValue(record.content) || extractTextFromValue(record.toolOutput);
}

function getMessageMetadata(message: AgentMessage): Record<string, unknown> {
  const record = message as Record<string, unknown>;
  return record.metadata && typeof record.metadata === "object"
    ? (record.metadata as Record<string, unknown>)
    : {};
}

function inferSourceName(message: AgentMessage): string {
  const record = message as Record<string, unknown>;
  const metadata = getMessageMetadata(message);
  const candidates = [
    metadata.source_name,
    metadata.sourceName,
    metadata.channelId,
    metadata.toolName,
    record.role,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return "session_message";
}

function inferSourceType(message: AgentMessage): string {
  const record = message as Record<string, unknown>;
  return record.role === "toolResult" ? "after_tool_call" : "before_prompt_build";
}

function replaceMessageContent(message: AgentMessage, replacementText: string): AgentMessage {
  const record = { ...(message as Record<string, unknown>) };
  const originalContent = record.content;
  const metadata = getMessageMetadata(message);

  record.metadata = {
    ...metadata,
    prism_redacted: true,
  };

  if (typeof originalContent === "string") {
    record.content = replacementText;
  } else if (Array.isArray(originalContent)) {
    record.content = [{ type: "text", text: replacementText }];
  } else if ("toolOutput" in record) {
    record.toolOutput = replacementText;
    record.content = [{ type: "text", text: replacementText }];
  } else {
    record.content = replacementText;
  }

  if ("details" in record) {
    delete record.details;
  }

  return record as AgentMessage;
}

function applyResponseToMessage(
  message: AgentMessage,
  response: PrismResponse,
  config: PluginConfig,
): AgentMessage | null {
  if (response.verdict === "ALLOW") {
    return message;
  }

  if (response.verdict === "QUARANTINE" && config.quarantineMode === "exclude") {
    return null;
  }

  const placeholder =
    response.placeholder ??
    (response.verdict === "BLOCK"
      ? "[PRISM_BLOCKED untrusted context removed before model assembly]"
      : "[PRISM_QUARANTINED suspicious context pending verification]");

  return replaceMessageContent(message, placeholder);
}

export class PrismContextEngine implements ContextEngine {
  readonly info = {
    id: "prism-context",
    name: "PRISM Context Engine",
    version: "0.1.0",
  };

  constructor(
    private readonly config: PluginConfig,
    private readonly logger: LoggerLike,
  ) {}

  async ingest(): Promise<IngestResult> {
    return { ingested: false };
  }

  async assemble(params: {
    sessionId: string;
    sessionKey?: string;
    messages: AgentMessage[];
    tokenBudget?: number;
  }): Promise<AssembleResult> {
    const messages: AgentMessage[] = [];

    for (const [index, message] of params.messages.entries()) {
      const text = getMessageText(message);
      if (!text.trim()) {
        messages.push(message);
        continue;
      }

      const sourceName = inferSourceName(message);
      if (isTrusted(sourceName)) {
        messages.push(message);
        continue;
      }

      const metadata = getMessageMetadata(message);
      const request: PrismRequest = {
        entry_id: `${params.sessionId}:${index}`,
        text,
        ingestion_path: mapSource(
          inferSourceType(message),
          typeof metadata.toolName === "string" ? metadata.toolName : undefined,
          sourceName,
        ),
        source_type: inferSourceType(message),
        source_name: sourceName,
        session_id: params.sessionId,
        run_id: params.sessionId,
        metadata,
      };

      // assemble() is the authoritative enforcement point — do not rely on ingest() alone.
      const response = await inspect(request, this.config);
      const rewritten = applyResponseToMessage(message, response, this.config);
      if (rewritten) {
        messages.push(rewritten);
      } else {
        this.logger.warn(
          `[openclaw-prism] excluded quarantined message from assembly session=${params.sessionId} source=${sourceName}`,
        );
      }
    }

    return {
      messages,
      estimatedTokens: 0,
    };
  }

  async compact(): Promise<CompactResult> {
    return {
      ok: true,
      compacted: false,
      reason: "prism_context_engine_noop_compaction",
    };
  }
}
