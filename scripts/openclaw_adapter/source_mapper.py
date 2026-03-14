from __future__ import annotations


def map_ingestion_path(source_type: str, source_name: str, metadata: dict | None) -> str:
    source_type = (source_type or "").strip().lower()
    source_name = (source_name or "").strip().lower()

    mapping = {
        "whatsapp": "network_responses",
        "telegram": "network_responses",
        "slack": "network_responses",
        "webchat": "network_responses",
        "web_search": "network_responses",
        "web_fetch": "network_responses",
        "external_api": "network_responses",
        "notifications": "notifications",
        "android_notif": "notifications",
        "attachment": "shared_storage",
        "imported_doc": "shared_storage",
        "sync_file": "shared_storage",
        "clipboard": "clipboard",
        "intent": "android_intents",
        "deep_link": "android_intents",
        "accessibility": "ui_accessibility",
        "ocr": "ui_accessibility",
        "screen_ui": "ui_accessibility",
        "ui": "ui_accessibility",
        "memory_chunk": "rag_store",
        "rag": "rag_store",
        "retrieval": "rag_store",
    }

    for candidate in (source_name, source_type):
        if candidate in mapping:
            return mapping[candidate]

    if metadata:
        tool_name = str(metadata.get("tool_name", "")).strip().lower()
        if tool_name in mapping:
            return mapping[tool_name]

    return "network_responses"

