package com.verifai.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
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

    public static final String ACTION_DETECT_URL = "DETECT_URL";
    public static final String ACTION_CLIPBOARD_RESULT = "CLIPBOARD_RESULT";
    public static final String EXTRA_AUTOMATION_CLICKED = "automation_clicked";
    public static final String SOURCE_TAP = "tap";
    public static final String SOURCE_AUTOMATION = "automation";

    /** Same-process handle so the accessibility service can push foreground-app changes. */
    public static volatile OverlayService instance;

    private WindowManager windowManager;
    private WindowManager.LayoutParams buttonParams;

    private View buttonView;
    private View resultView;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private volatile boolean detectionPending = false;
    private volatile String lastAnalyzedUrl = "";
    /** Clipboard content captured right before accessibility automation ran —
     *  lets us tell a freshly-copied link apart from stale leftovers. */
    private volatile String preAutomationClip = null;

    private final Runnable detectionTimeout = new Runnable() {
        @Override
        public void run() {
            if (!detectionPending) return;
            detectionPending = false;
            resetButton();
            showToastResult("⏱️ לא התקבלה תשובה", "real", "נסה שוב, או העתק קישור (Share ← Copy Link) ולחץ על הכפתור", 0);
        }
    };

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
        instance = this;
        try {
            startForegroundService();
            windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
            showButton();
            startGalleryWatcher();

            // If the accessibility service already knows which app is in front,
            // sync the button visibility immediately. (Play build has no
            // accessibility service — the button is simply always visible.)
            if (!BuildFlags.PLAY_BUILD) {
                String fg = VerifAIAccessibilityService.getForegroundPackage();
                if (fg != null) onForegroundApp(fg);
            }
        } catch (Throwable t) {
            // Never take the whole app process down — record and stop cleanly
            CrashLog.log(this, "OverlayService.onCreate", t);
            stopSelf();
        }
    }

    // ─── Foreground-app gating ───────────────────────────────────────────────

    /** Called by VerifAIAccessibilityService whenever the foreground app changes. */
    public static void notifyForegroundApp(String pkg) {
        OverlayService s = instance;
        if (s != null) s.onForegroundApp(pkg);
    }

    private void onForegroundApp(String pkg) {
        final boolean show = VerifAIAccessibilityService.SUPPORTED_PACKAGES.contains(pkg);
        mainHandler.post(() -> {
            if (buttonView != null) buttonView.setVisibility(show ? View.VISIBLE : View.GONE);
        });
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

    private void startForegroundService() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "AI Detector Overlay", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(ch);
        }
        Notification n = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("VerifAI active")
            .setContentText("The 🔍 button appears inside TikTok, Instagram, YouTube…")
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
        startForeground(1, n);
    }

    // ─── Floating Button (pinned top-side, hidden until a supported app opens) ──

    private TextView btnIcon;
    private TextView btnLabel;
    private android.widget.ProgressBar btnSpinner;

    private GradientDrawable buttonBg(boolean loading) {
        GradientDrawable bg = new GradientDrawable(
            GradientDrawable.Orientation.TL_BR,
            loading
                ? new int[]{Color.parseColor("#334155"), Color.parseColor("#1e293b")}
                : new int[]{Color.parseColor("#7c6cff"), Color.parseColor("#4f46e5")});
        bg.setShape(GradientDrawable.OVAL);
        bg.setStroke(dp(2), Color.parseColor("#66ffffff"));
        return bg;
    }

    private View buildButtonView() {
        FrameLayout root = new FrameLayout(this);
        root.setBackground(buttonBg(false));
        root.setElevation(dp(10));

        LinearLayout inner = new LinearLayout(this);
        inner.setOrientation(LinearLayout.VERTICAL);
        inner.setGravity(Gravity.CENTER);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(dp(58), dp(58));
        lp.gravity = Gravity.CENTER;
        inner.setLayoutParams(lp);

        btnIcon = new TextView(this);
        btnIcon.setText("AI?");
        btnIcon.setTextColor(Color.WHITE);
        btnIcon.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        btnIcon.setTypeface(Typeface.create("sans-serif-black", Typeface.BOLD));
        btnIcon.setGravity(Gravity.CENTER);

        btnLabel = new TextView(this);
        btnLabel.setText("VerifAI");
        btnLabel.setTextColor(Color.parseColor("#ccffffff"));
        btnLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 7);
        btnLabel.setTypeface(null, Typeface.BOLD);
        btnLabel.setGravity(Gravity.CENTER);
        btnLabel.setLetterSpacing(0.1f);

        btnSpinner = new android.widget.ProgressBar(this);
        btnSpinner.setIndeterminate(true);
        btnSpinner.setVisibility(View.GONE);
        FrameLayout.LayoutParams spLp = new FrameLayout.LayoutParams(dp(30), dp(30));
        spLp.gravity = Gravity.CENTER;
        btnSpinner.setLayoutParams(spLp);

        inner.addView(btnIcon);
        inner.addView(btnLabel);
        root.addView(inner);
        root.addView(btnSpinner);
        return root;
    }

    private void showButton() {
        // Dedup guard: never leave a previous button attached. If showButton is
        // ever reached twice (service re-created via START_STICKY, etc.) a second
        // addView would put a SECOND floating button on screen. Remove any
        // existing one first so there is always exactly one.
        if (buttonView != null) {
            try { windowManager.removeView(buttonView); } catch (Exception ignored) {}
            buttonView = null;
        }
        // Accessibility service may start us before the overlay permission is
        // We do NOT pre-check canDrawOverlays() — it lies on many OEM skins.
        // We just try to add the view; if the permission is genuinely missing
        // addView() throws, onCreate() catches it and stops the service, and the
        // JS side sees serviceRunning=false and opens Settings. If it succeeds,
        // the button is up regardless of what the flag claimed.
        buttonView = buildButtonView();

        buttonParams = new WindowManager.LayoutParams(
            dp(58), dp(58),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        );
        // Pinned to the screen edge; the user can drag it up/down and the
        // position is remembered across restarts.
        buttonParams.gravity = Gravity.TOP | Gravity.END;
        buttonParams.x = dp(8);
        buttonParams.y = getSharedPreferences("verifai_overlay", MODE_PRIVATE)
            .getInt("button_y", dp(140));

        attachDragAndTap(buttonView);
        // Visibility policy:
        //  • Accessibility ON  → the button appears ONLY inside supported apps
        //    (TikTok/Instagram/YouTube/Telegram/WhatsApp…) and hides everywhere
        //    else, so it never sits stuck on the home screen annoying the user.
        //    onForegroundApp() drives show/hide from here on.
        //  • Accessibility OFF → we can't know which app is in front, so the
        //    button stays visible (better an always-there button than an
        //    invisible one — this was the old "worked a second then vanished").
        boolean canDetectApp = VerifAIAccessibilityService.isConnected();
        boolean showNow = true;
        if (canDetectApp) {
            String fg = VerifAIAccessibilityService.getForegroundPackage();
            showNow = fg != null && VerifAIAccessibilityService.SUPPORTED_PACKAGES.contains(fg);
        }
        buttonView.setVisibility(showNow ? View.VISIBLE : View.GONE);
        windowManager.addView(buttonView, buttonParams);
    }

    /** Tap = detect. Vertical drag = move the button (position persisted).
     *  A plain OnClickListener can't coexist with dragging, so both gestures
     *  are resolved here from raw touch events. */
    private void attachDragAndTap(View v) {
        final int slop = android.view.ViewConfiguration.get(this).getScaledTouchSlop();
        v.setOnTouchListener(new View.OnTouchListener() {
            private float downRawY; private int startY; private boolean dragging;
            @Override public boolean onTouch(View view, android.view.MotionEvent e) {
                switch (e.getActionMasked()) {
                    case android.view.MotionEvent.ACTION_DOWN:
                        downRawY = e.getRawY();
                        startY = buttonParams.y;
                        dragging = false;
                        view.animate().scaleX(0.88f).scaleY(0.88f).setDuration(80).start();
                        return true;
                    case android.view.MotionEvent.ACTION_MOVE: {
                        float dy = e.getRawY() - downRawY;
                        if (!dragging && Math.abs(dy) > slop) dragging = true;
                        if (dragging) {
                            buttonParams.y = Math.max(dp(40), startY + (int) dy);
                            try { windowManager.updateViewLayout(view, buttonParams); } catch (Exception ignored) {}
                        }
                        return true;
                    }
                    case android.view.MotionEvent.ACTION_UP:
                        view.animate().scaleX(1f).scaleY(1f).setDuration(120).start();
                        if (dragging) {
                            getSharedPreferences("verifai_overlay", MODE_PRIVATE)
                                .edit().putInt("button_y", buttonParams.y).apply();
                        } else {
                            onButtonTapped();
                        }
                        return true;
                    case android.view.MotionEvent.ACTION_CANCEL:
                        view.animate().scaleX(1f).scaleY(1f).setDuration(120).start();
                        return true;
                }
                return false;
            }
        });
    }

    private void showLoading() {
        mainHandler.post(() -> {
            if (buttonView == null) return;
            buttonView.setBackground(buttonBg(true));
            btnIcon.setVisibility(View.GONE);
            btnLabel.setVisibility(View.GONE);
            btnSpinner.setVisibility(View.VISIBLE);
        });
    }

    private void resetButton() {
        mainHandler.post(() -> {
            if (buttonView == null) return;
            buttonView.setBackground(buttonBg(false));
            btnIcon.setVisibility(View.VISIBLE);
            btnLabel.setVisibility(View.VISIBLE);
            btnSpinner.setVisibility(View.GONE);
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
        conn.setReadTimeout(90000); // deep analysis can take 40s+
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

    /** Resolve a YouTube watch/shorts/youtu.be URL to a directly-downloadable
     *  progressive (muxed audio+video) MP4 URL, via the innertube ANDROID
     *  client. Runs ON THE PHONE — a residential IP — where YouTube's
     *  datacenter bot-wall does NOT apply, so we get the real file (and can
     *  then read its actual code/metadata) without any proxy. */
    private String resolveYouTubeCdnUrl(String pageUrl) {
        java.util.regex.Matcher m = java.util.regex.Pattern
            .compile("(?:v=|youtu\\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})").matcher(pageUrl);
        if (!m.find()) return null;
        String vid = m.group(1);
        try {
            String body = "{\"context\":{\"client\":{\"clientName\":\"ANDROID\","
                + "\"clientVersion\":\"19.44.38\",\"androidSdkVersion\":34,\"hl\":\"en\","
                + "\"osName\":\"Android\",\"osVersion\":\"14\"}},\"videoId\":\"" + vid
                + "\",\"contentCheckOk\":true,\"racyCheckOk\":true}";
            URL url = new URL("https://www.youtube.com/youtubei/v1/player?key="
                + "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("User-Agent",
                "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip");
            conn.setDoOutput(true);
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(12000);
            try (OutputStream os = conn.getOutputStream()) { os.write(body.getBytes("UTF-8")); }
            if (conn.getResponseCode() != 200) return null;
            StringBuilder sb = new StringBuilder();
            try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream()))) {
                String line; while ((line = br.readLine()) != null) sb.append(line);
            }
            JSONObject sd = new JSONObject(sb.toString()).optJSONObject("streamingData");
            if (sd == null) return null;
            JSONArray fmts = sd.optJSONArray("formats");   // progressive = muxed a+v
            if (fmts == null) return null;
            String best = null;
            for (int i = 0; i < fmts.length(); i++) {
                JSONObject f = fmts.getJSONObject(i);
                String mime = f.optString("mimeType", "");
                if (f.has("url") && mime.contains("mp4")) {   // has a direct (un-ciphered) URL
                    if (f.optInt("itag") == 18) return f.getString("url");  // 360p, small
                    if (best == null) best = f.optString("url", null);
                }
            }
            return best;
        } catch (Exception e) {
            return null;
        }
    }

    private JSONObject detectViaPhoneDownload(String videoUrl) throws Exception {
        // Step 1: resolve share/page URL to an actual downloadable CDN URL.
        String downloadUrl = videoUrl;
        String referer = "https://www.google.com/";
        if (videoUrl.contains("tiktok.com") || videoUrl.contains("vm.tiktok")) {
            String cdnUrl = resolveTikTokCdnUrl(videoUrl);
            if (cdnUrl != null) { downloadUrl = cdnUrl; referer = "https://www.tiktok.com/"; }
        } else if (videoUrl.contains("youtube.com") || videoUrl.contains("youtu.be")) {
            String cdnUrl = resolveYouTubeCdnUrl(videoUrl);
            if (cdnUrl == null) throw new Exception("youtube resolve failed");
            downloadUrl = cdnUrl; referer = "https://www.youtube.com/";
        }

        // Download video on phone (residential IP)
        java.io.File tmpFile = new java.io.File(getCacheDir(), "verifai_tmp.mp4");
        try {
            URL dlUrl = new URL(downloadUrl);
            HttpURLConnection dlConn = (HttpURLConnection) dlUrl.openConnection();
            dlConn.setRequestProperty("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15");
            dlConn.setRequestProperty("Referer", referer);
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
            upConn.setReadTimeout(90000); // deep analysis can take 40s+

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

    // ─── Local-file detection (Telegram / WhatsApp) ─────────────────────────

    /** Kick off reading the most-recently-saved video from the app the user is
     *  in (Telegram/WhatsApp). Falls back to the screen-capture path if no file
     *  is reachable. Reads the REAL code/metadata — the product's core promise. */
    private void detectViaLatestLocalVideo(final String pkg) {
        detectionPending = true;
        showLoading();
        mainHandler.removeCallbacks(detectionTimeout);
        mainHandler.postDelayed(detectionTimeout, 120000);
        executor.submit(() -> {
            try {
                java.io.File video = findLatestAppVideo(pkg);
                if (video == null) {
                    // File not reachable. Either the video isn't downloaded yet,
                    // or (most often) VerifAI doesn't have media access. The
                    // 100%-reliable path always works, so point at it.
                    if (!detectionPending) return;
                    mainHandler.post(OverlayService.this::finishDetection);
                    boolean tg = pkg != null && (pkg.contains("telegram") || pkg.contains("challegram"));
                    showToastResult("📥 לא הצלחתי לגשת לסרטון", "unknown",
                        tg ? "שמור אותו: ⋮ ← Save to Gallery, או שתף אותו ל-VerifAI (תמיד עובד)"
                           : "שתף את הסרטון ל-VerifAI (הכי אמין), או אפשר ל-VerifAI גישה למדיה בהגדרות", 0);
                    return;
                }
                JSONObject result = detectViaLocalFile(video);
                if (result == null) throw new Exception("no result");
                renderResult(result);
            } catch (Exception e) {
                if (!detectionPending) return;
                mainHandler.post(OverlayService.this::finishDetection);
                showToastResult("❌ הבדיקה נכשלה", "unknown", "נסה שוב", 0);
            }
        });
    }

    /** The exact folders WhatsApp/Telegram write received videos to. We scan
     *  these DIRECTLY (File API) rather than MediaStore, because WhatsApp drops a
     *  .nomedia file in its Media folders — so those videos are NOT indexed by
     *  MediaStore and a MediaStore query finds nothing. Android/media/<pkg>/ is
     *  readable by other apps on Android 11+. */
    private java.util.List<String> appVideoDirs(String pkg) {
        java.util.List<String> dirs = new java.util.ArrayList<>();
        if (pkg == null) return dirs;
        String ext;
        try { ext = android.os.Environment.getExternalStorageDirectory().getAbsolutePath(); }
        catch (Exception e) { ext = "/storage/emulated/0"; }
        if (pkg.contains("telegram") || pkg.contains("challegram")) {
            dirs.add(ext + "/Android/media/org.telegram.messenger/Telegram/Telegram Video");
            dirs.add(ext + "/Android/media/org.telegram.messenger.web/Telegram/Telegram Video");
            dirs.add(ext + "/Telegram/Telegram Video");
            dirs.add(ext + "/Android/media/org.telegram.plus/Telegram/Telegram Video");
        } else if (pkg.contains("whatsapp")) {
            dirs.add(ext + "/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video");
            dirs.add(ext + "/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video/Sent");
            dirs.add(ext + "/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Video");
            dirs.add(ext + "/WhatsApp/Media/WhatsApp Video");
        }
        return dirs;
    }

    private boolean isVideoFile(String name) {
        String n = name.toLowerCase();
        return n.endsWith(".mp4") || n.endsWith(".mkv") || n.endsWith(".webm")
            || n.endsWith(".mov") || n.endsWith(".3gp");
    }

    /** Newest video in the app's folders (optionally only if fresher than
     *  maxAgeMs; pass 0 for no age limit). Direct scan first, MediaStore as a
     *  fallback for OEMs that put media elsewhere. */
    private java.io.File findAppVideo(String pkg, long maxAgeMs) {
        java.io.File newest = null;
        long newestMod = 0;
        for (String d : appVideoDirs(pkg)) {
            java.io.File dir = new java.io.File(d);
            java.io.File[] files;
            try { files = dir.listFiles(); } catch (Exception e) { files = null; }
            if (files == null) continue;
            for (java.io.File f : files) {
                try {
                    if (f == null || !f.isFile() || !isVideoFile(f.getName())) continue;
                    if (f.length() < 50000) continue;
                    long mod = f.lastModified();
                    if (mod > newestMod) { newestMod = mod; newest = f; }
                } catch (Exception ignored) {}
            }
        }
        if (newest != null && newest.canRead()) {
            if (maxAgeMs <= 0) return newest;
            long age = System.currentTimeMillis() - newestMod;
            if (age >= 0 && age <= maxAgeMs) return newest;
            return null;   // a file exists but it's stale — not what the user is watching
        }
        // Fallback: MediaStore (works when the app has media visibility on).
        return findAppVideoViaMediaStore(pkg, maxAgeMs);
    }

    private java.io.File findLatestAppVideo(String pkg) { return findAppVideo(pkg, 0); }

    private java.io.File findAppVideoViaMediaStore(String pkg, long maxAgeMs) {
        String needle;
        if (pkg == null) return null;
        if (pkg.contains("telegram") || pkg.contains("challegram")) needle = "elegram";
        else if (pkg.contains("whatsapp")) needle = "hatsApp";
        else return null;
        String[] proj = {
            android.provider.MediaStore.Video.Media.DATA,
            android.provider.MediaStore.Video.Media.SIZE,
            android.provider.MediaStore.Video.Media.DATE_MODIFIED,
        };
        String sel = android.provider.MediaStore.Video.Media.DATA + " LIKE ?";
        String[] args = { "%" + needle + "%" };
        try (android.database.Cursor c = getContentResolver().query(
                android.provider.MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                proj, sel, args,
                android.provider.MediaStore.Video.Media.DATE_MODIFIED + " DESC")) {
            if (c != null && c.moveToFirst()) {
                String path = c.getString(0);
                long size = c.getLong(1);
                long modSec = c.getLong(2);
                if (path != null && size > 50000) {
                    java.io.File f = new java.io.File(path);
                    if (f.exists() && f.canRead()) {
                        if (maxAgeMs <= 0) return f;
                        long age = System.currentTimeMillis() - modSec * 1000L;
                        if (age >= 0 && age <= maxAgeMs) return f;
                    }
                }
            }
        } catch (Exception ignored) {}
        return null;
    }

    /** Upload a local video file to /detect and return the parsed result. */
    private JSONObject detectViaLocalFile(java.io.File file) throws Exception {
        String boundary = "VerifAILocal" + System.currentTimeMillis();
        URL uploadUrl = new URL(API + "/detect");
        HttpURLConnection upConn = (HttpURLConnection) uploadUrl.openConnection();
        upConn.setRequestMethod("POST");
        upConn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        upConn.setDoOutput(true);
        upConn.setConnectTimeout(10000);
        upConn.setReadTimeout(90000); // deep analysis can take 40s+

        try (OutputStream out = upConn.getOutputStream()) {
            String header = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\""
                + file.getName() + "\"\r\nContent-Type: video/mp4\r\n\r\n";
            out.write(header.getBytes("UTF-8"));
            try (java.io.FileInputStream fis = new java.io.FileInputStream(file)) {
                byte[] buf = new byte[65536]; int n; long total = 0;
                while ((n = fis.read(buf)) != -1) {
                    out.write(buf, 0, n);
                    total += n;
                    if (total > 30 * 1024 * 1024) break; // cap upload at 30MB
                }
            }
            out.write(("\r\n--" + boundary + "--\r\n").getBytes("UTF-8"));
        }

        if (upConn.getResponseCode() != 200) throw new Exception("Upload error " + upConn.getResponseCode());
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(upConn.getInputStream()))) {
            String line; while ((line = br.readLine()) != null) sb.append(line);
        }
        return new JSONObject(sb.toString());
    }

    // ─── Button Tap ─────────────────────────────────────────────────────────

    private void onButtonTapped() {
        if (detectionPending) {
            // Second tap while working = cancel. A button that ignores taps
            // reads as "stuck" — always give the user a way out.
            finishDetection();
            showToastResult("✋ הבדיקה בוטלה", "real", "לחץ שוב על הכפתור כדי לבדוק", 0);
            return;
        }
        if (BuildFlags.PLAY_BUILD) {
            // No accessibility automation here, and the clipboard can't be
            // trusted on its own (a stale link would answer the WRONG video) —
            // analyze what's actually on screen.
            startScreenCaptureFallback();
            return;
        }

        // Telegram / WhatsApp: the video the user is watching is a REAL file
        // already downloaded on the phone. Read its actual code/metadata instead
        // of screenshotting — a far stronger verdict. Needs the accessibility
        // service on so we know which app is in front.
        String fg = VerifAIAccessibilityService.getForegroundPackage();
        if (VerifAIAccessibilityService.isLocalFileApp(fg)) {
            detectViaLatestLocalVideo(fg);
            return;
        }

        detectionPending = true;
        showLoading();
        // Stage timeout: covers clipboard check + accessibility automation.
        // detectAndShow() reschedules it for the (slower) network stage.
        mainHandler.removeCallbacks(detectionTimeout);
        mainHandler.postDelayed(detectionTimeout, 12000);

        // Fast path: if the accessibility service can read the on-screen video's
        // link RIGHT NOW, grab it directly — skipping the clipboard-reader
        // activity flash. Removes the visible flicker and ~0.5-1s of delay, and
        // means a tap answers almost immediately.
        if (VerifAIAccessibilityService.grabCurrentVideoUrl()) {
            return; // comes back via SOURCE_AUTOMATION
        }

        // Accessibility is OFF (foreground app unknown): the user may have just
        // watched a Telegram/WhatsApp video, which is a REAL file freshly written
        // to the phone. Read that file's actual code — NOT a screenshot — as long
        // as it was touched in the last couple of minutes (so we don't grab a
        // stale, unrelated clip). This makes Telegram/WhatsApp work by-code even
        // without the accessibility service.
        if (fg == null) {
            executor.submit(() -> {
                try {
                    java.io.File recent = findRecentAppVideo(120000);
                    if (recent != null) {
                        // We're about to upload+analyze (can take ~40s+) — extend
                        // the stage timeout to the network budget so the short
                        // 12s timeout can't fire a false "no answer" mid-analysis.
                        mainHandler.removeCallbacks(detectionTimeout);
                        mainHandler.postDelayed(detectionTimeout, 120000);
                        JSONObject r = detectViaLocalFile(recent);
                        if (r != null) { renderResult(r); return; }
                    }
                } catch (Exception ignored) {}
                // Nothing readable → clipboard link (must read on the main thread
                // via the transparent activity; background reads are blocked).
                mainHandler.post(() -> launchClipboardReader(SOURCE_TAP));
            });
            return;
        }

        // Unsupported foreground app with accessibility on: the clipboard may
        // hold a link the user copied.
        launchClipboardReader(SOURCE_TAP);
    }

    /** Newest Telegram/WhatsApp video, but only if modified within {@code maxAgeMs}
     *  — i.e. the clip the user is almost certainly watching right now. Lets the
     *  by-code path work without the accessibility service telling us the app.
     *  Direct folder scan (handles WhatsApp's .nomedia) across both apps. */
    private java.io.File findRecentAppVideo(long maxAgeMs) {
        java.io.File tg = findAppVideo("org.telegram.messenger", maxAgeMs);
        java.io.File wa = findAppVideo("com.whatsapp", maxAgeMs);
        if (tg == null) return wa;
        if (wa == null) return tg;
        return tg.lastModified() >= wa.lastModified() ? tg : wa;
    }

    /** No link/file could be read (accessibility off + nothing copied). GUIDE the
     *  user instead of hijacking the screen with the capture-consent dialog that
     *  bounced them out to the home screen. The product reads the video's real
     *  code — accessibility is the reliable way to feed it a link hands-free. */
    private void guideNoVideo() {
        mainHandler.post(this::finishDetection);
        showToastResult("📋 לא נמצא סרטון לבדיקה", "unknown",
            "הדלק 'נגישות' בהגדרות VerifAI (זיהוי אוטומטי), או העתק קישור (Share ← Copy Link) ולחץ שוב", 0);
    }

    private void launchClipboardReader(String source) {
        try {
            Intent i = new Intent(this, ClipboardReaderActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
            i.putExtra(ClipboardReaderActivity.EXTRA_SOURCE, source);
            startActivity(i);
        } catch (Exception e) {
            finishDetection();
            showToastResult("❌ " + e.getMessage(), "real", "נסה שוב", 0);
        }
    }

    private String extractVideoUrl(String text) {
        if (text == null) return null;
        text = text.trim();
        if (!text.startsWith("http")) return null;
        for (Pattern p : VIDEO_PATTERNS) {
            if (p.matcher(text).find()) return text;
        }
        return null;
    }

    private void finishDetection() {
        detectionPending = false;
        mainHandler.removeCallbacks(detectionTimeout);
        resetButton();
    }

    private void handleClipboardResult(String text, String source, boolean automationClicked) {
        String url = extractVideoUrl(text);

        if (SOURCE_TAP.equals(source)) {
            // Accessibility automation copies the link of the video CURRENTLY on
            // screen, so it always beats the clipboard (which may hold a stale
            // link from yesterday and produce an answer for the wrong video).
            preAutomationClip = text;
            if (VerifAIAccessibilityService.grabCurrentVideoUrl()) {
                return; // comes back with SOURCE_AUTOMATION
            }
            if (url != null) {
                detectAndShow(url);
            } else {
                // No accessibility and no link in the clipboard — guide the user
                // rather than screen-capturing (which bounced them to home).
                guideNoVideo();
            }
        } else { // automation came back
            String preUrl = extractVideoUrl(preAutomationClip);
            if (url != null && (automationClicked || preUrl == null || url.equals(lastAnalyzedUrl))) {
                // Copy-Link actually got clicked (fresh link of the visible
                // video), or there was nothing stale to confuse it with, or the
                // user is re-checking the same video — all safe to analyze.
                detectAndShow(url);
            } else {
                // Automation never clicked Copy Link and the clipboard only has
                // the same old text — analyzing it would answer the WRONG video.
                guideNoVideo();
            }
        }
    }

    private void detectAndShow(final String url) {
        lastAnalyzedUrl = url;
        detectionPending = true;
        showLoading();
        // Network stage can take a while (phone download + upload + analysis)
        mainHandler.removeCallbacks(detectionTimeout);
        mainHandler.postDelayed(detectionTimeout, 120000);

        executor.submit(() -> {
            JSONObject result = null;

            // Attempt 1 — download on the PHONE (residential IP, not bot-walled)
            // and upload the real file. ONLY for hosts we can actually resolve to
            // a media URL on-device (TikTok, YouTube). Instagram et al. have no
            // phone resolver — downloading their page URL would upload HTML — so
            // they skip straight to the server, which resolves them via yt-dlp.
            boolean phoneDownloadable = url.contains("tiktok.com") || url.contains("vm.tiktok")
                || url.contains("youtube.com") || url.contains("youtu.be");
            if (phoneDownloadable) {
                try { result = detectViaPhoneDownload(url); }
                catch (Exception phoneFail) { result = null; }   // fall through to server
            }

            // Attempt 2 — hand the URL to the server (/detect-url): it has yt-dlp
            // + cobalt/mirror resolvers and can often fetch what the phone's
            // simple resolver couldn't (TikTok short links, Instagram, Twitter,
            // Facebook, Reddit…). This is what turns a failure into a verdict.
            if (result == null) {
                try { result = detectViaServerUrl(url); }
                catch (Exception serverFail) { result = null; }
            }

            if (result != null) {
                try { renderResult(result); return; }
                catch (Exception ignored) {}
            }

            // Both paths failed — but only surface it if this detection is still
            // current (the stage timeout / a cancel may have already ended it).
            if (!detectionPending) return;
            mainHandler.post(OverlayService.this::finishDetection);
            showToastResult("❌ לא הצלחתי לשלוף את הסרטון", "unknown",
                "נסה שוב, או פתח את הסרטון ← Share ← VerifAI (תמיד עובד)", 0);
        });
    }

    /** Map a detection JSON (from /detect, /detect-url or /detect-frame) to the
     *  floating result card. Shared by the URL and screen-frame paths. */
    private void renderResult(JSONObject result) throws Exception {
        // This detection may already be over — the stage timeout fired, or the
        // user second-tapped to cancel, or a newer detection started. In any of
        // those cases detectionPending is false; showing this (now stale) verdict
        // would flash a SECOND, contradictory toast. Drop it.
        if (!detectionPending) return;
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
        } else if ("suspicious".equals(verdict)) {
            title = "⚠️ חשוד — ייתכן AI";
        } else if ("unknown".equals(verdict)) {
            title = "❓ לא הצלחתי להכריע";
        } else {
            title = "✅ Authentic Footage";
        }
        String sub = pct + "% · " + (method.length() > 40 ? method.substring(0, 40) + "…" : method);

        mainHandler.post(this::finishDetection);
        showToastResult(title, verdict, sub, pct);
    }

    // ─── MediaProjection frame fallback ─────────────────────────────────────

    /** Called by ScreenCaptureService once it has a JPEG frame of the screen. */
    public static void onFrameCaptured(byte[] jpeg) {
        OverlayService s = instance;
        if (s != null) s.handleFrameCaptured(jpeg);
    }

    /** Called by ScreenCaptureService with a burst of JPEG frames (~0.6s apart). */
    public static void onFramesCaptured(java.util.ArrayList<byte[]> jpegs) {
        OverlayService s = instance;
        if (s == null || jpegs == null || jpegs.isEmpty()) return;
        if (jpegs.size() == 1) {
            s.handleFrameCaptured(jpegs.get(0)); // single frame → old endpoint
        } else {
            s.handleFramesCaptured(jpegs);
        }
    }

    /** Called by the accessibility service when the grab flow died and no
     *  clipboard result will ever arrive — unstick the button immediately. */
    public static void onAutomationFailed() {
        OverlayService s = instance;
        if (s == null) return;
        s.mainHandler.post(s::finishDetection);
        s.showToastResult("⚠️ הזיהוי האוטומטי נכשל", "real",
            "העתק קישור (Share ← Copy Link) ולחץ שוב", 0);
    }

    /** Called by the capture activity/service when capture couldn't happen. */
    public static void onFrameCaptureFailed(String reason) {
        OverlayService s = instance;
        if (s == null) return;
        s.mainHandler.post(s::finishDetection);
        s.showToastResult("📷 לא ניתן לצלם מסך", "real",
            (reason == null || reason.isEmpty()) ? "נסה שוב" : reason, 0);
    }

    /** Last resort when no video URL/file is obtainable: capture a screen frame. */
    private void startScreenCaptureFallback() {
        detectionPending = true;
        mainHandler.post(this::showLoading);
        mainHandler.removeCallbacks(detectionTimeout);
        mainHandler.postDelayed(detectionTimeout, 120000);
        try {
            Intent i = new Intent(this, MediaProjectionRequestActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
            startActivity(i);
        } catch (Exception e) {
            mainHandler.post(this::finishDetection);
            showToastResult("📷 לא ניתן לצלם מסך", "real", "נסה שוב", 0);
        }
    }

    private void handleFrameCaptured(final byte[] jpeg) {
        executor.submit(() -> {
            try {
                if (jpeg == null || jpeg.length == 0) throw new Exception("empty frame");
                JSONObject result = detectViaFrame(jpeg);
                if (result == null) throw new Exception("frame analysis failed");
                renderResult(result);
            } catch (Exception e) {
                mainHandler.post(this::finishDetection);
                showToastResult("❌ " + e.getMessage(), "real", "נסה שוב", 0);
            }
        });
    }

    private void handleFramesCaptured(final java.util.ArrayList<byte[]> jpegs) {
        executor.submit(() -> {
            try {
                JSONObject result;
                try {
                    result = detectViaFrames(jpegs);
                } catch (Exception burstFailed) {
                    // Server without /detect-frames (or transient error) —
                    // degrade to the single-frame path instead of failing.
                    result = detectViaFrame(jpegs.get(jpegs.size() / 2));
                }
                if (result == null) throw new Exception("frame analysis failed");
                renderResult(result);
            } catch (Exception e) {
                mainHandler.post(this::finishDetection);
                showToastResult("❌ " + e.getMessage(), "real", "נסה שוב", 0);
            }
        });
    }

    /** Upload a burst of JPEG frames to /detect-frames for temporal analysis. */
    private JSONObject detectViaFrames(java.util.List<byte[]> jpegs) throws Exception {
        String boundary = "VerifAIBoundary" + System.currentTimeMillis();
        URL uploadUrl = new URL(API + "/detect-frames");
        HttpURLConnection upConn = (HttpURLConnection) uploadUrl.openConnection();
        upConn.setRequestMethod("POST");
        upConn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        upConn.setDoOutput(true);
        upConn.setConnectTimeout(10000);
        upConn.setReadTimeout(90000);

        try (OutputStream out = upConn.getOutputStream()) {
            for (int i = 0; i < jpegs.size(); i++) {
                String header = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"files\"; filename=\"frame" + i + ".jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
                out.write(header.getBytes("UTF-8"));
                out.write(jpegs.get(i));
                out.write("\r\n".getBytes("UTF-8"));
            }
            out.write(("--" + boundary + "--\r\n").getBytes("UTF-8"));
        }

        if (upConn.getResponseCode() != 200) throw new Exception("Burst upload error " + upConn.getResponseCode());
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(upConn.getInputStream()))) {
            String line; while ((line = br.readLine()) != null) sb.append(line);
        }
        return new JSONObject(sb.toString());
    }

    private JSONObject detectViaFrame(byte[] jpeg) throws Exception {
        String boundary = "VerifAIBoundary" + System.currentTimeMillis();
        URL uploadUrl = new URL(API + "/detect-frame");
        HttpURLConnection upConn = (HttpURLConnection) uploadUrl.openConnection();
        upConn.setRequestMethod("POST");
        upConn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        upConn.setDoOutput(true);
        upConn.setConnectTimeout(10000);
        upConn.setReadTimeout(90000);

        try (OutputStream out = upConn.getOutputStream()) {
            String header = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"frame.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
            out.write(header.getBytes("UTF-8"));
            out.write(jpeg);
            out.write(("\r\n--" + boundary + "--\r\n").getBytes("UTF-8"));
        }

        if (upConn.getResponseCode() != 200) throw new Exception("Frame upload error " + upConn.getResponseCode());
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(upConn.getInputStream()))) {
            String line; while ((line = br.readLine()) != null) sb.append(line);
        }
        return new JSONObject(sb.toString());
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
            } else if ("suspicious".equals(verdict) || "unknown".equals(verdict)) {
                accentColor = Color.parseColor("#f59e0b");   // amber — not a clean bill of health
                bgColor     = Color.parseColor("#1a1203");
                badgeLabel  = "  INCONCLUSIVE";
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

            // Explicit ✕ — tap-anywhere-to-dismiss is invisible to users
            TextView close = new TextView(this);
            close.setText("✕");
            close.setTextColor(Color.parseColor("#99ffffff"));
            close.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
            close.setPadding(dp(10), dp(4), dp(4), dp(10));
            content.addView(close);

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

            card.setTranslationY(-dp(48));
            card.setAlpha(0f);
            windowManager.addView(resultView, resultParams);
            card.animate().translationY(0f).alpha(1f).setDuration(260).start();

            Runnable dismiss = () -> {
                final View v = resultView;
                if (v == null) return;
                resultView = null;
                v.animate().translationY(-dp(48)).alpha(0f).setDuration(200)
                    .withEndAction(() -> {
                        try { windowManager.removeView(v); } catch (Exception ignored) {}
                    }).start();
            };

            card.setOnClickListener(v -> dismiss.run());
            close.setOnClickListener(v -> dismiss.run());
            mainHandler.postDelayed(dismiss, 8000);
        });
    }

    private WindowManager.LayoutParams resultParams;

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
        instance = null;
        if (galleryWatcher != null) galleryWatcher.stop();
        try { if (buttonView != null) windowManager.removeView(buttonView); } catch (Exception ignored) {}
        try { if (resultView != null) windowManager.removeView(resultView); } catch (Exception ignored) {}
        executor.shutdownNow();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            if (intent != null && ACTION_DETECT_URL.equals(intent.getAction())) {
                // Direct request (e.g. from the accessibility service) with a known URL
                String url = intent.getStringExtra("url");
                if (url != null && !url.isEmpty()) {
                    detectAndShow(url);
                }
            } else if (intent != null && ACTION_CLIPBOARD_RESULT.equals(intent.getAction())) {
                // ClipboardReaderActivity finished reading the clipboard
                String text = intent.getStringExtra("text");
                String source = intent.getStringExtra(ClipboardReaderActivity.EXTRA_SOURCE);
                boolean clicked = intent.getBooleanExtra(EXTRA_AUTOMATION_CLICKED, false);
                handleClipboardResult(text, source != null ? source : SOURCE_TAP, clicked);
            }
        } catch (Throwable t) {
            CrashLog.log(this, "OverlayService.onStartCommand", t);
        }
        return START_STICKY;
    }
}
