package com.aivideodetector;

import android.app.Service;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.os.IBinder;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.Toast;
import androidx.annotation.Nullable;

/**
 * Android foreground service that draws a draggable floating button
 * over all other apps using SYSTEM_ALERT_WINDOW permission.
 *
 * Required in AndroidManifest.xml:
 *   <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
 *   <service android:name=".OverlayService" android:exported="false" />
 */
public class OverlayService extends Service {

    private WindowManager windowManager;
    private View overlayView;
    private WindowManager.LayoutParams params;

    private int initialX, initialY;
    private float initialTouchX, initialTouchY;
    private boolean isDragging = false;
    private static final int DRAG_THRESHOLD = 10;

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        createOverlayView();
    }

    private void createOverlayView() {
        overlayView = LayoutInflater.from(this).inflate(R.layout.overlay_button, null);

        params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;
        params.x = 20;
        params.y = 300;

        overlayView.setOnTouchListener((view, event) -> {
            switch (event.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    initialX = params.x;
                    initialY = params.y;
                    initialTouchX = event.getRawX();
                    initialTouchY = event.getRawY();
                    isDragging = false;
                    return true;

                case MotionEvent.ACTION_MOVE:
                    float dx = event.getRawX() - initialTouchX;
                    float dy = event.getRawY() - initialTouchY;
                    if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
                        isDragging = true;
                    }
                    if (isDragging) {
                        params.x = initialX + (int) dx;
                        params.y = initialY + (int) dy;
                        windowManager.updateViewLayout(overlayView, params);
                    }
                    return true;

                case MotionEvent.ACTION_UP:
                    if (!isDragging) {
                        onButtonTapped();
                    }
                    return true;
            }
            return false;
        });

        windowManager.addView(overlayView, params);
    }

    private void onButtonTapped() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard == null || !clipboard.hasPrimaryClip()) {
            Toast.makeText(this, "Copy a video link first, then tap AI Detector", Toast.LENGTH_SHORT).show();
            return;
        }

        String text = "";
        try {
            text = clipboard.getPrimaryClip().getItemAt(0).coerceToText(this).toString();
        } catch (Exception e) {
            // ignore
        }

        if (text.startsWith("http")) {
            // Broadcast URL to the React Native layer for analysis
            Intent intent = new Intent("com.aivideodetector.ANALYZE_URL");
            intent.putExtra("url", text);
            sendBroadcast(intent);

            Toast.makeText(this, "Analyzing...", Toast.LENGTH_SHORT).show();
        } else {
            Toast.makeText(this, "No video URL in clipboard. Copy a video link first.", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (overlayView != null) {
            windowManager.removeView(overlayView);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }
}
