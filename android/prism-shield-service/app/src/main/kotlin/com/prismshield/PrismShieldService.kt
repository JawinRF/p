package com.prismshield

import fi.iki.elonen.NanoHTTPD
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

/**
 * PrismShieldService — foreground service that:
 *  1. Runs HTTP sidecar on localhost:8766 (on-device dashboard & Layer 1+2)
 *  2. Hooks clipboard changes
 *  3. Receives broadcast intents for notification scan results
 *
 * The Python sidecar (port 8765) provides the full 3-layer pipeline.
 * This on-device service provides real-time monitoring and Layer 1+2 defense.
 *   POST to http://localhost:8766/v1/inspect
 *   Body: { "path": "clipboard|notification|rag|document|...", "content": "..." }
 *   Response: { "verdict": "ALLOW"|"BLOCK", "score": 0.0-1.0, "rules": [...] }
 */
class PrismShieldService : Service() {

    companion object {
        const val PORT            = 8766
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

        startHttpSidecarNano()
        hookClipboard()
        registerNotifReceiver()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        serviceScope.cancel()
        httpServer?.stop()
        classifier.close()
    }

    // ── HTTP Sidecar (NanoHTTPD) ──────────────────────────────────────────────

    private var httpServer: NanoHTTPD? = null

    private fun startHttpSidecarNano() {
        val svc = self
        httpServer = object : NanoHTTPD(PORT) {
            override fun serve(session: IHTTPSession): Response {
                val uri = session.uri
                val body = try {
                    val map = mutableMapOf<String, String>()
                    session.parseBody(map)
                    map["postData"] ?: ""
                } catch (e: Exception) { "" }

                val responseJson = when (uri) {
                    "/v1/inspect" -> kotlinx.coroutines.runBlocking { svc.handleInspect(body) }
                    "/v1/guard"   -> svc.handleGuard(body)
                    "/v1/status"  -> kotlinx.coroutines.runBlocking { svc.handleStatus() }
                    else          -> """{"error":"unknown endpoint"}"""
                }
                return newFixedLengthResponse(Response.Status.OK, "application/json", responseJson)
            }
        }
        httpServer?.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
        android.util.Log.i("PrismShield", "NanoHTTPD sidecar listening on :$PORT")
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
                ?.getText()
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
