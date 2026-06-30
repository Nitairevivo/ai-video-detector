package com.verifai.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public class OverlayService extends Service {

    private static final String API = "https://ai-video-detector-production-a305.up.railway.app";
    private static final String CHANNEL_ID = "overlay_service";

    private WindowManager windowManager;
    private WindowManager.LayoutParams buttonParams;
    private WindowManager.LayoutParams resultParams;

    private View buttonView;
    private View resultView;

    private int initialX, initialY;
    private float initialTouchX, initialTouchY;
    private boolean isDragging = false;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private static final Pattern[] VIDEO_PATTERNS = {
        Pattern.compile("tiktok\\.com"),
        Pattern.compile("instagram\\.com/(reel|p|tv)/"),
        Pattern.compile("youtube\\.com/(shorts|watch)"),
        Pattern.compile("youtu\\.be/"),
        Pattern.compile("twitter\\.com/.*/status"),
        Pattern.compile("x\\.com/.*/status"),
        Pattern.compile("facebook\\.com/(watch|reel|videos)"),
        Pattern.compile("fb\\.watch/"),
    };

    @Nullable
    @Override
    public IBinder onBind(Intent intent) { return null; }

    private GalleryWatcher galleryWatcher;

    @Override
    public void onCreate() {
        super.onCreate();
        try {
            startForegroundNotification();
            windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
            showButton();
            startGalleryWatcher();
        } catch (Exception e) {
            stopSelf();
        }
    }

    private void startGalleryWatcher() {
        galleryWatcher = new GalleryWatcher(this, new GalleryWatcher.DetectionCallback() {
            @Override
            public void onResult(String filePath, String verdict, float confidence, String method) {
                int pct = Math.round(confidence * 100);
                String title;
                if ("ai_generated".equals(verdict)) {
                    title = "🤖 AI Generated";
                } else if ("ai_edited".equals(verdict)) {
                    title = "✏️ Real Video, AI Edited";
                } else {
                    title = "✅ Authentic Footage";
                }
                String sub = pct + "% · " + (method.length() > 40 ? method.substring(0, 40) + "…" : method);
                showToastResult(title, verdict, sub, pct);
            }

            @Override
            public void onError(String filePath, String error) {
                // Silent fail — don't disturb the user
            }
        });
        galleryWatcher.start();
    }

    // ─── Foreground Notification ────────────────────────────────────────────

    private void startForegroundNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "AI Detector Overlay", NotificationManager.IMPORTANCE_LOW);
                ch.setShowBadge(false);
                ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(ch);
            } catch (Exception ignored) {}
        }
        Notification n;
        try {
            n = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("AI Detector active")
                .setContentText("Tap the floating button to check any video")
                .setSmallIcon(android.R.drawable.ic_menu_search)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
        } catch (Exception e) {
            n = new Notification();
        }
        // Android 14+ requires specifying foreground service type; fall back to 2-arg if it fails
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            try {
                startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
                return;
            } catch (Exception ignored) {
                // Fall through to 2-arg which always succeeds
            }
        }
        startForeground(1, n);
    }

    // ─── Floating Button ────────────────────────────────────────────────────

    private View buildButtonView() {
        FrameLayout root = new FrameLayout(this);

        GradientDrawable bg = new GradientDrawable();
        bg.setShape(GradientDrawable.OVAL);
        bg.setColor(Color.parseColor("#6366f1"));
        bg.setSize(dp(60), dp(60));
        // shadow not available on old API, elevation on FrameLayout
        root.setBackground(bg);
        root.setElevation(dp(12));

        LinearLayout inner = new LinearLayout(this);
        inner.setOrientation(LinearLayout.VERTICAL);
        inner.setGravity(Gravity.CENTER);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(dp(60), dp(60));
        lp.gravity = Gravity.CENTER;
        inner.setLayoutParams(lp);

        TextView icon = new TextView(this);
        icon.setText("🔍");
        icon.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        icon.setGravity(Gravity.CENTER);

        TextView label = new TextView(this);
        label.setText("AI?");
        label.setTextColor(Color.WHITE);
        label.setTextSize(TypedValue.COMPLEX_UNIT_SP, 8);
        label.setTypeface(null, Typeface.BOLD);
        label.setGravity(Gravity.CENTER);
        label.setLetterSpacing(0.08f);

        inner.addView(icon);
        inner.addView(label);
        root.addView(inner);
        return root;
    }

    private void showButton() {
        buttonView = buildButtonView();

        buttonParams = new WindowManager.LayoutParams(
            dp(64), dp(64),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        );
        buttonParams.gravity = Gravity.TOP | Gravity.START;
        buttonParams.x = 20;
        buttonParams.y = 300;

        buttonView.setOnTouchListener((v, e) -> {
            switch (e.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    initialX = buttonParams.x;
                    initialY = buttonParams.y;
                    initialTouchX = e.getRawX();
                    initialTouchY = e.getRawY();
                    isDragging = false;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = e.getRawX() - initialTouchX;
                    float dy = e.getRawY() - initialTouchY;
                    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) isDragging = true;
                    if (isDragging) {
                        buttonParams.x = initialX + (int) dx;
                        buttonParams.y = initialY + (int) dy;
                        windowManager.updateViewLayout(buttonView, buttonParams);
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                    if (!isDragging) onButtonTapped();
                    return true;
            }
            return false;
        });

        windowManager.addView(buttonView, buttonParams);
    }

    private void showLoading() {
        mainHandler.post(() -> {
            View icon = buttonView.findViewWithTag("icon");
            if (buttonView instanceof FrameLayout) {
                LinearLayout inner = (LinearLayout) ((FrameLayout) buttonView).getChildAt(0);
                ((TextView) inner.getChildAt(0)).setText("⏳");
                ((TextView) inner.getChildAt(1)).setText("...");
                GradientDrawable bg = new GradientDrawable();
                bg.setShape(GradientDrawable.OVAL);
                bg.setColor(Color.parseColor("#4b5563"));
                bg.setSize(dp(60), dp(60));
                buttonView.setBackground(bg);
            }
        });
    }

    private void resetButton() {
        mainHandler.post(() -> {
            if (buttonView instanceof FrameLayout) {
                LinearLayout inner = (LinearLayout) ((FrameLayout) buttonView).getChildAt(0);
                ((TextView) inner.getChildAt(0)).setText("🔍");
                ((TextView) inner.getChildAt(1)).setText("AI?");
                GradientDrawable bg = new GradientDrawable();
                bg.setShape(GradientDrawable.OVAL);
                bg.setColor(Color.parseColor("#6366f1"));
                bg.setSize(dp(60), dp(60));
                buttonView.setBackground(bg);
            }
        });
    }

    // ─── Detection helpers ───────────────────────────────────────────────────

    private JSONObject detectViaServerUrl(String videoUrl) throws Exception {
        JSONObject json = new JSONObject();
        json.put("url", videoUrl);
        URL apiUrl = new URL(API + "/detect-url");
        HttpURLConnection conn = (HttpURLConnection) apiUrl.openConnection();
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setDoOutput(true);
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(30000);
        try (OutputStream os = conn.getOutputStream()) { os.write(json.toString().getBytes("UTF-8")); }
        if (conn.getResponseCode() != 200) throw new Exception("Server error " + conn.getResponseCode());
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream()))) {
            String line; while ((line = br.readLine()) != null) sb.append(line);
        }
        return new JSONObject(sb.toString());
    }

    private String resolveTikTokCdnUrl(String shareUrl) {
        // Extract video ID from TikTok share URL
        java.util.regex.Pattern p = java.util.regex.Pattern.compile("/video/(\\d+)");
        java.util.regex.Matcher m = p.matcher(shareUrl);
        if (!m.find()) return null;
        String videoId = m.group(1);

        // Call TikTok's internal API to get CDN URL (works from phone with residential IP)
        String[] apiEndpoints = {
            "https://api19-normal-c-useast1a.tiktokv.com/aweme/v1/feed/?aweme_id=" + videoId,
            "https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/?aweme_id=" + videoId,
        };

        for (String apiUrl : apiEndpoints) {
            try {
                URL url = new URL(apiUrl);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestProperty("User-Agent",
                    "com.zhiliaoapp.musically/2022600040 (Linux; U; Android 9; en_US; SM-G973F; Build/PPR1.180610.011; Cronet/TTNetVersion:6c7b701a 2021-08-23)");
                conn.setRequestProperty("Accept", "application/json");
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(10000);

                if (conn.getResponseCode() == 200) {
                    java.io.BufferedReader br = new java.io.BufferedReader(
                        new java.io.InputStreamReader(conn.getInputStream()));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = br.readLine()) != null) sb.append(line);

                    JSONObject data = new JSONObject(sb.toString());
                    JSONArray awemes = data.optJSONArray("aweme_list");
                    if (awemes != null && awemes.length() > 0) {
                        JSONObject aweme = awemes.getJSONObject(0);
                        JSONObject video = aweme.optJSONObject("video");
                        if (video != null) {
                            JSONObject playAddr = video.optJSONObject("play_addr");
                            if (playAddr != null) {
                                JSONArray urls = playAddr.optJSONArray("url_list");
                                if (urls != null && urls.length() > 0) {
                                    return urls.getString(0);
                                }
                            }
                        }
                    }
                }
            } catch (Exception ignored) {}
        }
        return null;
    }

    private JSONObject detectViaPhoneDownload(String videoUrl) throws Exception {
        // Step 1: If TikTok, resolve share URL to actual CDN video URL
        String downloadUrl = videoUrl;
        if (videoUrl.contains("tiktok.com") || videoUrl.contains("vm.tiktok")) {
            String cdnUrl = resolveTikTokCdnUrl(videoUrl);
            if (cdnUrl != null) {
                downloadUrl = cdnUrl;
            }
        }

        // Download video on phone (residential IP)
        java.io.File tmpFile = new java.io.File(getCacheDir(), "verifai_tmp.mp4");
        try {
            URL dlUrl = new URL(downloadUrl);
            HttpURLConnection dlConn = (HttpURLConnection) dlUrl.openConnection();
            dlConn.setRequestProperty("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
            dlConn.setRequestProperty("Referer", "https://www.tiktok.com/");
            dlConn.setConnectTimeout(15000);
            dlConn.setReadTimeout(30000);
            dlConn.setInstanceFollowRedirects(true);

            if (dlConn.getResponseCode() != 200) throw new Exception("Download failed: " + dlConn.getResponseCode());

            try (java.io.InputStream in = dlConn.getInputStream();
                 java.io.FileOutputStream fos = new java.io.FileOutputStream(tmpFile)) {
                byte[] buf = new byte[65536];
                int n; long total = 0;
                while ((n = in.read(buf)) != -1) {
                    fos.write(buf, 0, n);
                    total += n;
                    if (total > 30 * 1024 * 1024) break; // max 30MB
                }
            }

            // Upload file to /detect
            String boundary = "VerifAIBoundary" + System.currentTimeMillis();
            URL uploadUrl = new URL(API + "/detect");
            HttpURLConnection upConn = (HttpURLConnection) uploadUrl.openConnection();
            upConn.setRequestMethod("POST");
            upConn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
            upConn.setDoOutput(true);
            upConn.setConnectTimeout(10000);
            upConn.setReadTimeout(30000);

            try (OutputStream out = upConn.getOutputStream()) {
                String header = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n";
                out.write(header.getBytes("UTF-8"));
                try (java.io.FileInputStream fis = new java.io.FileInputStream(tmpFile)) {
                    byte[] buf = new byte[65536]; int n;
                    while ((n = fis.read(buf)) != -1) out.write(buf, 0, n);
                }
                out.write(("\r\n--" + boundary + "--\r\n").getBytes("UTF-8"));
            }

            if (upConn.getResponseCode() != 200) throw new Exception("Upload error " + upConn.getResponseCode());
            StringBuilder sb = new StringBuilder();
            try (BufferedReader br = new BufferedReader(new InputStreamReader(upConn.getInputStream()))) {
                String line; while ((line = br.readLine()) != null) sb.append(line);
            }
            return new JSONObject(sb.toString());
        } finally {
            tmpFile.delete();
        }
    }

    // ─── Button Tap ─────────────────────────────────────────────────────────

    private void onButtonTapped() {
        ClipboardManager cb = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (cb == null || !cb.hasPrimaryClip()) {
            showToastResult("📋 Copy a video link first!", "real", "In TikTok: Share → Copy Link", 0);
            return;
        }
        String text = "";
        try {
            text = cb.getPrimaryClip().getItemAt(0).coerceToText(this).toString().trim();
        } catch (Exception e) { return; }

        if (!text.startsWith("http")) {
            showToastResult("📋 No URL found in clipboard", "real", "Copy a video link first", 0);
            return;
        }

        boolean isVideo = false;
        for (Pattern p : VIDEO_PATTERNS) {
            if (p.matcher(text).find()) { isVideo = true; break; }
        }
        if (!isVideo) {
            showToastResult("⚠️ URL not recognized", "real", text.length() > 50 ? text.substring(0, 50) + "…" : text, 0);
            return;
        }

        showLoading();
        final String url = text;
        executor.submit(() -> {
            try {
                JSONObject result;

                // For TikTok/Instagram: download on PHONE (residential IP, not blocked)
                // then upload file to API. For others: use server-side /detect-url.
                boolean isTikTok = url.contains("tiktok.com") || url.contains("instagram.com") || url.contains("vm.tiktok");
                if (isTikTok) {
                    result = detectViaPhoneDownload(url);
                } else {
                    result = detectViaServerUrl(url);
                }

                if (result == null) throw new Exception("Detection failed");
                String verdict = result.optString("verdict", result.optBoolean("is_ai_generated", false) ? "ai_generated" : "real");
                double confidence = result.getDouble("confidence");
                String tool = result.optString("ai_tool_detected", "");
                String editTool = result.optString("edit_tool_detected", "");
                String method = result.optString("detection_method", "");
                int pct = (int) Math.round(confidence * 100);

                String title;
                if ("ai_generated".equals(verdict)) {
                    title = (tool != null && !tool.isEmpty()) ? "🤖 AI · " + tool : "🤖 AI Generated";
                } else if ("ai_edited".equals(verdict)) {
                    title = (editTool != null && !editTool.isEmpty()) ? "✏️ Edited · " + editTool : "✏️ Real Video, AI-Edited";
                } else {
                    title = "✅ Authentic Footage";
                }
                String sub = pct + "% · " + (method.length() > 40 ? method.substring(0, 40) + "…" : method);

                showToastResult(title, verdict, sub, pct);

            } catch (Exception e) {
                resetButton();
                mainHandler.post(() -> showToastResult("❌ Error: " + e.getMessage(), "real", "Check your connection", 0));
            }
        });
    }

    // ─── Result Card (shown over other apps) ────────────────────────────────

    private void showToastResult(String title, String verdict, String subtitle, int pct) {
        resetButton();
        mainHandler.post(() -> {
            if (resultView != null) {
                try { windowManager.removeView(resultView); } catch (Exception ignored) {}
                resultView = null;
            }

            int accentColor, bgColor;
            String badgeLabel;
            if ("ai_generated".equals(verdict)) {
                accentColor = Color.parseColor("#ef4444");
                bgColor     = Color.parseColor("#1a0505");
                badgeLabel  = "  AI GENERATED";
            } else if ("ai_edited".equals(verdict)) {
                accentColor = Color.parseColor("#a855f7");
                bgColor     = Color.parseColor("#0e0516");
                badgeLabel  = "  AI EDITED";
            } else {
                accentColor = Color.parseColor("#22c55e");
                bgColor     = Color.parseColor("#031a0a");
                badgeLabel  = "  AUTHENTIC";
            }

            // Root card
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            GradientDrawable cardBg = new GradientDrawable();
            cardBg.setShape(GradientDrawable.RECTANGLE);
            cardBg.setColor(bgColor);
            cardBg.setCornerRadius(dp(16));
            cardBg.setStroke(dp(1), (accentColor & 0x00FFFFFF) | 0x55000000);
            card.setBackground(cardBg);
            card.setElevation(dp(20));
            card.setPadding(0, 0, 0, 0);
            card.setClipToOutline(true);

            // Top color bar
            View bar = new View(this);
            bar.setBackgroundColor(accentColor);
            LinearLayout.LayoutParams barLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(3));
            card.addView(bar, barLp);

            // Content row
            LinearLayout content = new LinearLayout(this);
            content.setOrientation(LinearLayout.HORIZONTAL);
            content.setGravity(Gravity.CENTER_VERTICAL);
            content.setPadding(dp(14), dp(12), dp(14), dp(14));
            content.setWeightSum(1);

            // Left side
            LinearLayout left = new LinearLayout(this);
            left.setOrientation(LinearLayout.VERTICAL);
            left.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout.LayoutParams leftLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            left.setLayoutParams(leftLp);

            // Badge
            LinearLayout badge = new LinearLayout(this);
            badge.setOrientation(LinearLayout.HORIZONTAL);
            badge.setGravity(Gravity.CENTER_VERTICAL);
            badge.setPadding(dp(8), dp(3), dp(8), dp(3));
            GradientDrawable badgeBg = new GradientDrawable();
            badgeBg.setShape(GradientDrawable.RECTANGLE);
            badgeBg.setColor((accentColor & 0x00FFFFFF) | 0x22000000);
            badgeBg.setCornerRadius(dp(20));
            badge.setBackground(badgeBg);

            View dot = new View(this);
            dot.setBackgroundColor(accentColor);
            GradientDrawable dotBg = new GradientDrawable();
            dotBg.setShape(GradientDrawable.OVAL);
            dotBg.setColor(accentColor);
            dotBg.setSize(dp(6), dp(6));
            dot.setBackground(dotBg);
            badge.addView(dot, new LinearLayout.LayoutParams(dp(6), dp(6)));

            TextView badgeText = new TextView(this);
            badgeText.setText(badgeLabel);
            badgeText.setTextColor(accentColor);
            badgeText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 9);
            badgeText.setTypeface(null, Typeface.BOLD);
            badgeText.setLetterSpacing(0.08f);
            badge.addView(badgeText);
            left.addView(badge);

            // Title
            TextView titleView = new TextView(this);
            titleView.setText(title);
            titleView.setTextColor(Color.WHITE);
            titleView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
            titleView.setTypeface(null, Typeface.BOLD);
            titleView.setPadding(0, dp(5), 0, dp(3));
            left.addView(titleView);

            // Subtitle
            TextView subView = new TextView(this);
            subView.setText(subtitle);
            subView.setTextColor(Color.parseColor("#888888"));
            subView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
            subView.setMaxLines(2);
            left.addView(subView);

            content.addView(left);

            // Confidence circle (only when we have pct > 0)
            if (pct > 0) {
                FrameLayout circle = new FrameLayout(this);
                GradientDrawable circleBg = new GradientDrawable();
                circleBg.setShape(GradientDrawable.OVAL);
                circleBg.setColor(Color.TRANSPARENT);
                circleBg.setStroke(dp(2), accentColor);
                circleBg.setSize(dp(60), dp(60));
                circle.setBackground(circleBg);
                circle.setLayoutParams(new LinearLayout.LayoutParams(dp(60), dp(60)));

                LinearLayout circleInner = new LinearLayout(this);
                circleInner.setOrientation(LinearLayout.VERTICAL);
                circleInner.setGravity(Gravity.CENTER);
                circleInner.setLayoutParams(new FrameLayout.LayoutParams(dp(60), dp(60)));

                TextView pctView = new TextView(this);
                pctView.setText(pct + "%");
                pctView.setTextColor(accentColor);
                pctView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
                pctView.setTypeface(null, Typeface.BOLD);
                pctView.setGravity(Gravity.CENTER);

                TextView confView = new TextView(this);
                confView.setText("conf.");
                confView.setTextColor(Color.parseColor("#666666"));
                confView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 8);
                confView.setGravity(Gravity.CENTER);

                circleInner.addView(pctView);
                circleInner.addView(confView);
                circle.addView(circleInner);
                content.addView(circle);
            }

            card.addView(content);
            resultView = card;

            resultParams = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT
            );
            resultParams.gravity = Gravity.TOP | Gravity.START;
            resultParams.x = 12;
            resultParams.y = 60;
            resultParams.width = -1; // match parent minus margins

            windowManager.addView(resultView, resultParams);

            // Tap to dismiss
            card.setOnClickListener(v -> {
                try { windowManager.removeView(resultView); } catch (Exception ignored) {}
                resultView = null;
            });

            // Auto-dismiss after 7s
            mainHandler.postDelayed(() -> {
                if (resultView != null) {
                    try { windowManager.removeView(resultView); } catch (Exception ignored) {}
                    resultView = null;
                }
            }, 7000);
        });
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    private int dp(int val) {
        return (int) TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, val,
            getResources().getDisplayMetrics()
        );
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (galleryWatcher != null) galleryWatcher.stop();
        try { if (buttonView != null) windowManager.removeView(buttonView); } catch (Exception ignored) {}
        try { if (resultView != null) windowManager.removeView(resultView); } catch (Exception ignored) {}
        executor.shutdownNow();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Called by VerifAIAccessibilityService with a URL to detect
        if (intent != null && "DETECT_URL".equals(intent.getAction())) {
            String url = intent.getStringExtra("url");
            if (url != null && !url.isEmpty()) {
                showLoading();
                final String finalUrl = url;
                executor.submit(() -> {
                    try {
                        JSONObject json = new JSONObject();
                        json.put("url", finalUrl);
                        URL apiUrl = new URL(API + "/detect-url");
                        HttpURLConnection conn = (HttpURLConnection) apiUrl.openConnection();
                        conn.setRequestMethod("POST");
                        conn.setRequestProperty("Content-Type", "application/json");
                        conn.setDoOutput(true);
                        conn.setConnectTimeout(10000);
                        conn.setReadTimeout(20000);
                        try (OutputStream os = conn.getOutputStream()) {
                            os.write(json.toString().getBytes("UTF-8"));
                        }
                        if (conn.getResponseCode() != 200) throw new Exception("Server error " + conn.getResponseCode());
                        StringBuilder sb = new StringBuilder();
                        try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream()))) {
                            String line; while ((line = br.readLine()) != null) sb.append(line);
                        }
                        JSONObject result = new JSONObject(sb.toString());
                        String verdict2 = result.optString("verdict", result.optBoolean("is_ai_generated", false) ? "ai_generated" : "real");
                        int pct = (int) Math.round(result.getDouble("confidence") * 100);
                        String tool = result.optString("ai_tool_detected", "");
                        String editTool2 = result.optString("edit_tool_detected", "");
                        String method = result.optString("detection_method", "");
                        String title;
                        if ("ai_generated".equals(verdict2)) {
                            title = (tool != null && !tool.isEmpty()) ? "🤖 AI · " + tool : "🤖 AI Generated";
                        } else if ("ai_edited".equals(verdict2)) {
                            title = (editTool2 != null && !editTool2.isEmpty()) ? "✏️ Edited · " + editTool2 : "✏️ Real Video, AI-Edited";
                        } else {
                            title = "✅ Authentic Footage";
                        }
                        String sub = pct + "% · " + (method.length() > 40 ? method.substring(0, 40) + "…" : method);
                        showToastResult(title, verdict2, sub, pct);
                    } catch (Exception e) {
                        resetButton();
                        mainHandler.post(() -> showToastResult("❌ " + e.getMessage(), "real", "Check connection", 0));
                    }
                });
            }
        }
        return START_STICKY;
    }
}
