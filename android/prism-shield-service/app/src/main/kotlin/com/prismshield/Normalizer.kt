package com.prismshield

import android.util.Base64
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * Normalizer — port of normalizer.py
 *
 * De-obfuscates text before it reaches Layer 1/2 scanners.
 * Strips: URL encoding, Base64, invisible Unicode, ANSI escape codes,
 *         HTML tags, homoglyphs, excessive whitespace.
 *
 * Called by PrismShieldService before PrismDetector.scan().
 */
object Normalizer {

    // ── Invisible / zero-width Unicode ────────────────────────────────────────
    private val INVISIBLE_UNICODE = Regex(
        "[\u00AD\u200B\u200C\u200D\u200E\u200F\uFEFF\u2060\u2061\u2062\u2063]"
    )

    // ── ANSI escape sequences ─────────────────────────────────────────────────
    private val ANSI_ESCAPE = Regex("\u001B\\[[0-9;]*[mGKHF]")

    // ── HTML / XML tags ───────────────────────────────────────────────────────
    private val HTML_TAGS = Regex("<[^>]{0,200}>")

    // ── Repeated whitespace ───────────────────────────────────────────────────
    private val MULTI_SPACE = Regex("[ \\t]{2,}")

    // ── Cyrillic / Greek homoglyphs → Latin equivalents ───────────────────────
    // Common confusables used in injection attacks
    private val HOMOGLYPH_MAP = mapOf(
        'а' to 'a', 'е' to 'e', 'о' to 'o', 'р' to 'p', 'с' to 'c',
        'х' to 'x', 'і' to 'i', 'ѕ' to 's', 'ԁ' to 'd', 'ɡ' to 'g',
        'А' to 'A', 'В' to 'B', 'Е' to 'E', 'К' to 'K', 'М' to 'M',
        'Н' to 'H', 'О' to 'O', 'Р' to 'P', 'С' to 'C', 'Т' to 'T',
        'Х' to 'X', 'ʏ' to 'Y'
    )

    data class NormResult(
        val text: String,
        val transformsApplied: List<String>
    )

    fun normalize(raw: String): NormResult {
        var text = raw
        val transforms = mutableListOf<String>()

        // 1. URL decode (handles %20, %2F, etc.)
        try {
            val decoded = URLDecoder.decode(text, StandardCharsets.UTF_8.name())
            if (decoded != text) { text = decoded; transforms += "url_decode" }
        } catch (_: Exception) {}

        // 2. Base64 decode — only if it looks like a pure b64 payload
        //    (avoids mangling regular text with accidental b64-like substrings)
        val b64Candidate = Regex("^[A-Za-z0-9+/]{20,}={0,2}$")
        if (b64Candidate.matches(text.trim())) {
            try {
                val decoded = Base64.decode(text.trim(), Base64.DEFAULT)
                    .toString(StandardCharsets.UTF_8)
                if (decoded.any { it.isLetterOrDigit() }) {
                    text = decoded; transforms += "base64_decode"
                }
            } catch (_: Exception) {}
        }

        // 3. Strip ANSI escape sequences
        val noAnsi = ANSI_ESCAPE.replace(text, "")
        if (noAnsi != text) { text = noAnsi; transforms += "strip_ansi" }

        // 4. Strip HTML/XML tags
        val noHtml = HTML_TAGS.replace(text, " ")
        if (noHtml != text) { text = noHtml; transforms += "strip_html" }

        // 5. Remove invisible Unicode characters
        val noInvis = INVISIBLE_UNICODE.replace(text, "")
        if (noInvis != text) { text = noInvis; transforms += "strip_invisible_unicode" }

        // 6. Map homoglyphs to Latin equivalents
        val mapped = text.map { HOMOGLYPH_MAP[it] ?: it }.joinToString("")
        if (mapped != text) { text = mapped; transforms += "homoglyph_map" }

        // 7. Collapse excessive whitespace
        text = MULTI_SPACE.replace(text, " ").trim()

        return NormResult(text, transforms)
    }
}
