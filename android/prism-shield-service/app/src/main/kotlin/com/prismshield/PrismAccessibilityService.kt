package com.prismshield

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.*

/**
 * Accessibility service that wires WindowContextBridge into the PRISM pipeline.
 *
 * On every window/content change:
 *   1. WindowContextBridge captures visible nodes
 *   2. Normalizer de-obfuscates the text
 *   3. PrismDetector (Layer 1) scans
 *   4. If uncertain, OnnxClassifier (Layer 2) classifies
 *   5. Result written to audit log
 *
 * Throttled to 750 ms (matches WindowContextBridge default).
 */
class PrismAccessibilityService : AccessibilityService() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var classifier: OnnxClassifier
    private lateinit var bridge: WindowContextBridge

    override fun onServiceConnected() {
        super.onServiceConnected()
        classifier = OnnxClassifier(this)
        bridge = WindowContextBridge(this)

        serviceInfo = serviceInfo.apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED or
                    AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            notificationTimeout = 750L   // mirror WindowContextBridge throttle
            flags = AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val root = rootInActiveWindow ?: return
        scope.launch {
            try {
                // 1. Capture screen context via the existing bridge
                val screenCtx    = bridge.captureScreenContext() ?: return@launch
                val payload      = bridge.buildInspectPayload(screenCtx)
                val rawText      = payload.optString("text", "")
                if (rawText.isBlank()) return@launch

                // 2. Normalise
                val norm = Normalizer.normalize(rawText)

                // 3. Layer 1
                val l1 = PrismDetector.scan(norm.text)

                // 4. Layer 2 (only in uncertain zone)
                val l2Prob = if (l1.score in 0.2f..0.7f) {
                    classifier.classify(norm.text).maliciousProb
                } else {
                    if (l1.verdict == PrismDetector.Verdict.BLOCK) 1.0f else 0.0f
                }

                val verdict = when {
                    l1.verdict == PrismDetector.Verdict.BLOCK -> "BLOCK"
                    l2Prob >= 0.70f                           -> "BLOCK"
                    else                                      -> "ALLOW"
                }

                // 5. Audit log
                MemShieldDb.get(this@PrismAccessibilityService).auditDao().insert(
                    AuditEntry(
                        path         = "ui_accessibility",
                        snippet      = norm.text.take(120),
                        verdict      = verdict,
                        layer1Score  = l1.score,
                        layer2Prob   = l2Prob,
                        matchedRules = l1.matchedRules.joinToString(",")
                    )
                )
            } catch (e: Exception) {
                // Swallow — service must not crash on bad node trees
            } finally {
                root.recycle()
            }
        }
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
        classifier.close()
    }
}
