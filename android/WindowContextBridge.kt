/**
 * WindowContextBridge
 * -------------------
 * Runs as part of the AccessibilityService. On each accessibility event,
 * collects the current window state and writes a JSON ScreenContext to a
 * Unix domain socket at SOCKET_PATH.
 *
 * The Python PRISM Shield process reads from this socket via
 * window_context_reader.py.
 */

package com.samsung.prismshield  // Assuming package, replace if needed

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import java.io.File
import java.net.UnixDomainSocketAddress  // API 33+; use LocalServerSocket for lower APIs

class WindowContextBridge(private val service: AccessibilityService) {

    companion object {
        const val SOCKET_PATH = "/data/local/tmp/prism_window_ctx.sock"
        // Throttle: only emit if >50ms since last emission (avoid flooding)
        const val EMIT_THROTTLE_MS = 50L
    }

    private var lastEmitTime = 0L
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    fun onAccessibilityEvent() {
        val now = System.currentTimeMillis()
        if (now - lastEmitTime < EMIT_THROTTLE_MS) return
        lastEmitTime = now
        scope.launch { emitContext() }
    }

    private suspend fun emitContext() = withContext(Dispatchers.IO) {
        val windows = service.windows ?: return@withContext
        val activeWindow = windows.firstOrNull { it.isActive } ?: return@withContext
        val rootNode = activeWindow.root ?: return@withContext

        // Collect visible nodes recursively
        val visibleNodes = mutableListOf<JsonObject>()
        collectVisibleNodes(rootNode, visibleNodes, depth = 0, maxDepth = 8)
        rootNode.recycle()

        // Build package + activity info
        val foregroundPackage  = activeWindow.root?.packageName?.toString() ?: "unknown"
        val windowType         = activeWindow.type

        val ctx = buildJsonObject {
            put("foreground_package",  foregroundPackage)
            put("foreground_activity", "")   // fill from ActivityManager if needed
            put("window_type",         windowType)
            put("screen_width_px",     service.resources.displayMetrics.widthPixels)
            put("screen_height_px",    service.resources.displayMetrics.heightPixels)
            put("visible_nodes",       JsonArray(visibleNodes))
        }

        // Write to socket (newline-terminated)
        writeToSocket(ctx.toString() + "\n")
    }

    private fun collectVisibleNodes(
        node: AccessibilityNodeInfo,
        out: MutableList<JsonObject>,
        depth: Int, maxDepth: Int
    ) {
        if (depth > maxDepth) return
        if (!node.isVisibleToUser) return   // hard filter — only visible nodes

        val bounds = android.graphics.Rect()
        node.getBoundsInScreen(bounds)
        // Skip off-screen and micro-bounds nodes (same logic as UIExtractor Stage A+B)
        if (bounds.left < 0 || bounds.top < 0) return
        val area = (bounds.right - bounds.left) * (bounds.bottom - bounds.top)
        if (area < 50) return

        val text = node.text?.toString() ?: ""
        val desc = node.contentDescription?.toString() ?: ""

        if (text.isNotBlank() || desc.isNotBlank()) {
            out.add(buildJsonObject {
                put("resource_id",  node.viewIdResourceName ?: "")
                put("class_name",   node.className?.toString() ?: "")
                put("text",         text)
                put("content_desc", desc)
                put("bounds_px",    JsonArray(listOf(bounds.left, bounds.top,
                                                      bounds.right, bounds.bottom)
                                                     .map { JsonPrimitive(it) }))
            })
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            collectVisibleNodes(child, out, depth + 1, maxDepth)
            child.recycle()
        }
    }

    private fun writeToSocket(data: String) {
        // LocalSocket for pre-API33 compatibility
        try {
            val client = android.net.LocalSocket()
            client.connect(android.net.LocalSocketAddress(
                SOCKET_PATH, android.net.LocalSocketAddress.Namespace.FILESYSTEM
            ))
            client.outputStream.write(data.toByteArray(Charsets.UTF_8))
            client.outputStream.flush()
            client.close()
        } catch (e: Exception) {
            // Service not connected yet — silently drop
        }
    }

    fun destroy() { scope.cancel() }
}
