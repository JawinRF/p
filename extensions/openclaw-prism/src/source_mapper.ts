const NETWORK = new Set([
  "whatsapp",
  "telegram",
  "slack",
  "webchat",
  "web_search",
  "web_fetch",
  "external_api",
]);

const NOTIFICATIONS = new Set(["notifications", "android_notif"]);
const STORAGE = new Set(["attachment", "imported_doc", "sync_file"]);
const CLIPBOARD = new Set(["clipboard"]);
const INTENTS = new Set(["intent", "deep_link"]);
const UI = new Set(["accessibility", "ocr", "screen_ui", "ui"]);
const MEMORY = new Set(["memory_chunk", "rag", "retrieval"]);
const TRUSTED = new Set(["system_prompt", "operator_config", "plugin_code", "bootstrap"]);

export function mapSource(event: string, toolName?: string, sourceName?: string): string {
  const candidates = [sourceName, toolName, event]
    .map((value) => (value ?? "").trim().toLowerCase())
    .filter(Boolean);

  for (const candidate of candidates) {
    if (NETWORK.has(candidate)) return "network_responses";
    if (NOTIFICATIONS.has(candidate)) return "notifications";
    if (STORAGE.has(candidate)) return "shared_storage";
    if (CLIPBOARD.has(candidate)) return "clipboard";
    if (INTENTS.has(candidate)) return "android_intents";
    if (UI.has(candidate)) return "ui_accessibility";
    if (MEMORY.has(candidate)) return "rag_store";
  }

  return "network_responses";
}

export function isTrusted(sourceName: string): boolean {
  return TRUSTED.has((sourceName ?? "").trim().toLowerCase());
}

