package com.prismshield

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Hooks ALL incoming notifications.
 * Extracts text and forwards to PrismShieldService via broadcast.
 *
 * Must be declared in AndroidManifest.xml with BIND_NOTIFICATION_LISTENER_SERVICE permission.
 * User must grant via: Settings > Notifications > Notification Access
 */
class PrismNotificationListener : NotificationListenerService() {

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val extras = sbn?.notification?.extras ?: return
        val title = extras.getCharSequence("android.title")?.toString() ?: ""
        val text  = extras.getCharSequence("android.text")?.toString()  ?: ""
        val full  = "$title $text".trim()

        if (full.isBlank()) return

        // Forward to PrismShieldService for Layer 1/2 scan
        sendBroadcast(Intent(PrismShieldService.ACTION_NOTIF_TEXT).apply {
            `package` = packageName
            putExtra(PrismShieldService.EXTRA_TEXT, full)
        })
    }
}
