package com.prismshield

import android.app.*
import android.content.*
import android.content.ClipboardManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.*
import java.net.ServerSocket
import java.net.Socket

/**
 * PrismShieldService — foreground service that:
 *  1. Runs HTTP sidecar on localhost:8765 (OpenClaw calls this)
 *  2. Hooks clipboard changes
 *  3. Receives broadcast intents for notification scan results
 *
 * OpenClaw integration (no changes to OpenClaw needed):
 *   Before assembling any prompt, POST to http://localhost:8765/v1/inspect
 *   Body: { "path": "clipboard|notification|rag|document|...", "content": "..." }
 *   Response: { "verdict": "ALLOW"|"BLOCK", "score": 0.0-1.0, "rules": [...] }
 */
class PrismShieldService : Service() {

    companion object {
        const val PORT            = 8765
        const val NOTIF_CHANNEL   = "prism_channel"
        const val NOTIF_ID        = 1
        const val TAG             = "PrismShield"

        // Broadcast action sent by PrismNotificationListener
        const val ACTION_NOTIF_TEXT = "com.prismshield.NOTIFICATION_TEXT"
        const val EXTRA_TEXT        = "text"
    }

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var classifier: OnnxClassifier
    private lateinit var memShield: MemShield
    private val self: PrismShieldService get() = this   // safe capture for coroutines

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification("PRISM Shield active"))

        classifier = OnnxClassifier(this)
        memShield  = MemShield(this)

        serviceScope.launch { startHttpSidecar() }
        hookClipboard()
        registerNotifReceiver()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        serviceScope.cancel()
        classifier.close()
    }

    // ── HTTP Sidecar ──────────────────────────────────────────────────────────

    private suspend fun startHttpSidecar() = withContext(Dispatchers.IO) {
        val server = ServerSocket(PORT)
        Log.i(TAG, "HTTP sidecar listening on :$PORT")

        while (isActive) {
            try {
                val socket = server.accept()
                launch { handleRequest(socket) }
            } catch (e: Exception) {
                Log.e(TAG, "Sidecar error: ${e.message}")
            }
        }
    }

    private suspend fun handleRequest(socket: Socket) = withContext(Dispatchers.IO) {
        try {
            val reader  = BufferedReader(InputStreamReader(socket.getInputStream()))
            val writer  = PrintWriter(socket.getOutputStream(), true)

            // Read HTTP request (minimal parser)
            val requestLine = reader.readLine() ?: return@withContext
            val headers = mutableMapOf<String, String>()
            var line: String?
            while (reader.readLine().also { line = it } != null && line!!.isNotEmpty()) {
                val parts = line!!.split(": ", limit = 2)
                if (parts.size == 2) headers[parts[0].lowercase()] = parts[1]
            }

            val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
            val bodyChars = CharArray(contentLength)
            reader.read(bodyChars)
            val body = String(bodyChars)

            val path = requestLine.split(" ").getOrNull(1) ?: "/"
            val responseJson = when {
                path == "/v1/inspect" -> handleInspect(body)
                path == "/v1/guard"   -> handleGuard(body)
                path == "/v1/status"  -> handleStatus()
                else                  -> """{"error":"unknown endpoint"}"""
            }

            // Write HTTP response
            writer.print("HTTP/1.1 200 OK\r\n")
            writer.print("Content-Type: application/json\r\n")
            writer.print("Content-Length: ${responseJson.length}\r\n")
            writer.print("\r\n")
            writer.print(responseJson)
            writer.flush()

        } catch (e: Exception) {
            Log.e(TAG, "Request error: ${e.message}")
        } finally {
            socket.close()
        }
    }

    // POST /v1/inspect  — PRISM + MemShield scan
    private suspend fun handleInspect(body: String): String {
        val json    = JSONObject(body)
        val path    = json.optString("path", "unknown")
        val content = json.optString("content", "")

        // Layer 1
        val l1 = PrismDetector.scan(content)

        // Layer 2 — only if L1 is uncertain (score 0.2–0.7)
        val l2Prob = if (l1.score in 0.2f..0.7f) {
            classifier.classify(content).maliciousProb
        } else {
            if (l1.verdict == PrismDetector.Verdict.BLOCK) 1.0f else 0.0f
        }

        val finalVerdict = when {
            l1.verdict == PrismDetector.Verdict.BLOCK -> "BLOCK"
            l2Prob >= 0.70f                           -> "BLOCK"
            else                                      -> "ALLOW"
        }

        // Audit log
        MemShieldDb.get(self).auditDao().insert(
            AuditEntry(
                path         = path,
                snippet      = content.take(120),
                verdict      = finalVerdict,
                layer1Score  = l1.score,
                layer2Prob   = l2Prob,
                matchedRules = l1.matchedRules.joinToString(",")
            )
        )

        updateNotification(finalVerdict)

        return JSONObject().apply {
            put("verdict", finalVerdict)
            put("score",   l1.score)
            put("l2_prob", l2Prob)
            put("rules",   l1.matchedRules.joinToString(","))
        }.toString()
    }

    // POST /v1/guard  — PII Guard on agent actions
    private fun handleGuard(body: String): String {
        val json    = JSONObject(body)
        val type    = json.optString("action_type", "")
        val payload = json.optString("action_payload", "")
        val intent  = json.optString("user_intent", "")

        val result = PiiGuard.check(type, payload, intent)

        return JSONObject().apply {
            put("verdict", result.verdict.name)
            put("reason",  result.reason)
        }.toString()
    }

    // GET /v1/status
    private suspend fun handleStatus(): String {
        val blocked = MemShieldDb.get(this).auditDao().blockedCount()
        return JSONObject().apply {
            put("status",        "running")
            put("port",          PORT)
            put("total_blocked", blocked)
        }.toString()
    }

    // ── Clipboard Hook ────────────────────────────────────────────────────────

    private fun hookClipboard() {
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.addPrimaryClipChangedListener {
            val text = clipboard.primaryClip
                ?.getItemAt(0)
                ?.getText(contentResolver)
                ?.toString() ?: return@addPrimaryClipChangedListener

            serviceScope.launch {
                val l1 = PrismDetector.scan(text)
                if (l1.verdict == PrismDetector.Verdict.BLOCK) {
                    Log.w(TAG, "Clipboard poison blocked: ${text.take(80)}")
                    MemShieldDb.get(this@PrismShieldService).auditDao().insert(
                        AuditEntry(
                            path         = "clipboard",
                            snippet      = text.take(120),
                            verdict      = "BLOCK",
                            layer1Score  = l1.score,
                            layer2Prob   = 0f,
                            matchedRules = l1.matchedRules.joinToString(",")
                        )
                    )
                    // Optionally clear clipboard
                    (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
                        .clearPrimaryClip()
                }
            }
        }
    }

    // ── Notification Receiver (works with PrismNotificationListener) ──────────

    private fun registerNotifReceiver() {
        val filter = IntentFilter(ACTION_NOTIF_TEXT)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(notifReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(notifReceiver, filter)
        }
    }

    private val notifReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val text = intent?.getStringExtra(EXTRA_TEXT) ?: return
            serviceScope.launch {
                val l1 = PrismDetector.scan(text)
                MemShieldDb.get(self).auditDao().insert(
                    AuditEntry(
                        path         = "notification",
                        snippet      = text.take(120),
                        verdict      = l1.verdict.name,
                        layer1Score  = l1.score,
                        layer2Prob   = 0f,
                        matchedRules = l1.matchedRules.joinToString(",")
                    )
                )
            }
        }
    }

    // ── Notification helpers ──────────────────────────────────────────────────

    private fun createNotificationChannel() {
        val chan = NotificationChannel(
            NOTIF_CHANNEL, "PRISM Shield", NotificationManager.IMPORTANCE_LOW
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(chan)
    }

    private fun buildNotification(text: String): Notification =
        Notification.Builder(this, NOTIF_CHANNEL)
            .setContentTitle("PRISM Shield")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .build()

    private fun updateNotification(verdict: String) {
        if (verdict == "BLOCK") {
            val nm = getSystemService(NotificationManager::class.java)
            nm.notify(NOTIF_ID, buildNotification("ALERT: Threat BLOCKED"))
        }
    }
}
