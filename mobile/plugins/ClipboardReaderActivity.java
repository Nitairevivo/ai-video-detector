package com.verifai.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

/**
 * Invisible, focus-grabbing activity that reads the clipboard and reports the
 * text back to OverlayService. Needed because Android 10+ only lets the app
 * with input focus read the clipboard — a background service gets nothing.
 */
public class ClipboardReaderActivity extends Activity {

    public static final String EXTRA_SOURCE = "source";
    public static final String EXTRA_TEXT = "text";

    private boolean sent = false;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            // Safety: never linger even if we somehow don't get window focus
            handler.postDelayed(() -> send(null), 1500);
        } catch (Throwable t) {
            CrashLog.log(this, "ClipboardReaderActivity.onCreate", t);
            finish();
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (!hasFocus || sent) return;

        String text = null;
        try {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null && cm.hasPrimaryClip()) {
                ClipData clip = cm.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {
                    CharSequence cs = clip.getItemAt(0).coerceToText(this);
                    if (cs != null) text = cs.toString().trim();
                }
            }
        } catch (Exception ignored) {}
        send(text);
    }

    private void send(String text) {
        if (sent) return;
        sent = true;
        handler.removeCallbacksAndMessages(null);
        try {
            Intent i = new Intent(this, OverlayService.class);
            i.setAction(OverlayService.ACTION_CLIPBOARD_RESULT);
            i.putExtra(EXTRA_TEXT, text);
            i.putExtra(EXTRA_SOURCE, getIntent().getStringExtra(EXTRA_SOURCE));
            startService(i);
        } catch (Exception ignored) {}
        finish();
        overridePendingTransition(0, 0);
    }
}
