import { PluginConfig, PrismRequest, PrismResponse, SidecarHealth } from "./types.js";

function syntheticResponse(verdict: "ALLOW" | "BLOCK", reason: string): PrismResponse {
  return {
    verdict,
    confidence: verdict === "BLOCK" ? 1 : 0,
    reason,
    layer_triggered: "SidecarClient",
    normalized_text: "",
    ticket_id: null,
    placeholder:
      verdict === "BLOCK"
        ? "[PRISM_BLOCKED untrusted context removed before model assembly]"
        : null,
    audit: {
      path: "network_responses",
      source_type: "sidecar_client",
      degraded: true,
    },
  };
}

function buildHeaders(config: PluginConfig): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (config.secret) {
    headers["X-PRISM-Secret"] = config.secret;
  }
  return headers;
}

export async function inspect(
  request: PrismRequest,
  config: PluginConfig,
): Promise<PrismResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);

  try {
    const response = await fetch(`${config.sidecarUrl}/v1/inspect`, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`sidecar_${response.status}`);
    }

    return (await response.json()) as PrismResponse;
  } catch {
    return config.failClosed
      ? syntheticResponse("BLOCK", "sidecar_error")
      : syntheticResponse("ALLOW", "sidecar_error_allow");
  } finally {
    clearTimeout(timeout);
  }
}

export async function getTicket(ticketId: string, config: PluginConfig): Promise<unknown | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);

  try {
    const response = await fetch(`${config.sidecarUrl}/v1/ticket/${ticketId}`, {
      method: "GET",
      headers: buildHeaders(config),
      signal: controller.signal,
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as unknown;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getHealth(config: PluginConfig): Promise<SidecarHealth | null> {
  try {
    const response = await fetch(`${config.sidecarUrl}/health`);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as SidecarHealth;
  } catch {
    return null;
  }
}
