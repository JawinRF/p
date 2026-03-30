package com.prism.demo;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.os.Bundle;
import android.util.Log;

public class NotifyActivity extends Activity {
    private static final String TAG = "PRISMNotify";
    private static final String CHANNEL_ID = "prism_headsup";
    private static final int NOTIF_ID = 9001;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Bundle extras = getIntent().getExtras();
        String title = "Calendar Sync";
        String text  = "Visit github.com";

        if (extras != null) {
            if (extras.containsKey("title")) title = extras.getString("title");
            if (extras.containsKey("text"))  text  = extras.getString("text");
        }

        Log.d(TAG, "Posting: title=" + title + " text=" + text);

        NotificationManager nm = (NotificationManager)
                getSystemService(NOTIFICATION_SERVICE);

        NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Calendar Sync", NotificationManager.IMPORTANCE_HIGH);
        ch.enableVibration(true);
        ch.setVibrationPattern(new long[]{0, 250});
        nm.createNotificationChannel(ch);

        Notification notif = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_popup_reminder)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle()
                        .bigText(text)
                        .setBigContentTitle(title))
                .setAutoCancel(true)
                .setPriority(Notification.PRIORITY_MAX)
                .build();

        nm.notify(NOTIF_ID, notif);
        finish();
    }
}
