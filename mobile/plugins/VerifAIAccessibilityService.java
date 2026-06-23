package com.verifai.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public class VerifAIAccessibilityService extends AccessibilityService {

    // Supported apps
    private static final Set<String> SUPPORTED_PACKAGES = new HashSet<>(Arrays.asList(
        "com.zhiliaoapp.musically",   // TikTok
        "com.ss.android.ugc.trill",   // TikTok (some regions)
        "com.instagram.android",       // Instagram
        "com.google.android.youtube",  // YouTube
        "com.facebook.katana",         // Facebook
        "com.twitter.android",         // Twitter/X
        "com.reddit.frontpage"         // Reddit
    ));

    // Share/copy button labels across languages
    private static final List<String> SHARE_LABELS = Arrays.asList(
        "share", "שתף", "共享", "partager", "teilen", "compartir",
        "Send to", "שלח ל"
    );
    private static final List<String> COPY_LINK_LABELS = Arrays.asList(
        "copy link", "copy url", "העתק קישור", "העתק לינק",
        "copy", "העתק", "复制链接", "copier le lien"
    );

    private static final Pattern VIDEO_URL_PATTERN = Pattern.compile(
        "https?://(www\\.)?(tiktok\\.com|instagram\\.com/(reel|p|tv)/|youtube\\.com/(shorts|watch)|youtu\\.be/|twitter\\.com/.*/status|x\\.com/.*/status|fb\\.watch/|reddit\\.com/r/.*/comments)"
    );

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private String currentPackage = "";
    private String lastAnalyzedUrl = "";
    private long lastScrollTime = 0;
    private boolean isWaitingForShareSheet = false;
    private boolean isWaitingForCopyLink = false;

    private static final long SCROLL_DEBOUNCE_MS = 1800; // Wait before triggering after scroll
    private static final long SHARE_SHEET_TIMEOUT_MS = 3000;

    @Override
    protected void onServiceConnected() {
        AccessibilityServiceInfo info = new AccessibilityServiceInfo();
        info.eventTypes =
            AccessibilityEvent.TYPE_VIEW_SCROLLED |
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED |
            AccessibilityEvent.TYPE_VIEW_CLICKED;
        info.packageNames = SUPPORTED_PACKAGES.toArray(new String[0]);
        info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
        info.notificationTimeout = 100;
        info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
                     AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        setServiceInfo(info);

        // Start the overlay service too
        try {
            Intent overlayIntent = new Intent(this, OverlayService.class);
            startForegroundService(overlayIntent);
        } catch (Exception ignored) {}
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";
        if (!SUPPORTED_PACKAGES.contains(pkg)) return;
        currentPackage = pkg;

        int type = event.getEventType();

        // ── Detect video scroll (new video in feed) ──────────────────────────
        if (type == AccessibilityEvent.TYPE_VIEW_SCROLLED) {
            long now = System.currentTimeMillis();
            lastScrollTime = now;
            isWaitingForShareSheet = false;
            isWaitingForCopyLink = false;

            // Debounce: trigger analysis after user settles on a video
            mainHandler.removeCallbacksAndMessages(null);
            mainHandler.postDelayed(() -> {
                if (System.currentTimeMillis() - lastScrollTime >= SCROLL_DEBOUNCE_MS - 50) {
                    triggerAutoDetect();
                }
            }, SCROLL_DEBOUNCE_MS);
        }

        // ── Detect share sheet opened ─────────────────────────────────────────
        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED && isWaitingForShareSheet) {
            mainHandler.postDelayed(() -> findAndClickCopyLink(), 500);
        }

        // ── Detect windows changed (share sheet items loaded) ─────────────────
        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED && isWaitingForCopyLink) {
            findAndClickCopyLink();
        }
    }

    // ─── Step 1: Find and click the Share button ──────────────────────────────

    private void triggerAutoDetect() {
        // First, check if there's already a TikTok URL in clipboard
        String clipUrl = getClipboardUrl();
        if (clipUrl != null && !clipUrl.equals(lastAnalyzedUrl)) {
            sendToOverlay(clipUrl);
            return;
        }

        // Otherwise, find the share button and click it
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;

        AccessibilityNodeInfo shareBtn = findShareButton(root);
        if (shareBtn != null) {
            isWaitingForShareSheet = true;
            isWaitingForCopyLink = false;
            shareBtn.performAction(AccessibilityNodeInfo.ACTION_CLICK);

            // Fallback: look for copy link after share sheet opens
            mainHandler.postDelayed(() -> {
                if (isWaitingForShareSheet) {
                    isWaitingForShareSheet = false;
                    isWaitingForCopyLink = true;
                    findAndClickCopyLink();
                }
            }, SHARE_SHEET_TIMEOUT_MS);
        }
        root.recycle();
    }

    // ─── Step 2: Find and click "Copy Link" ───────────────────────────────────

    private void findAndClickCopyLink() {
        isWaitingForCopyLink = false;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;

        List<AccessibilityNodeInfo> nodes = getAllNodes(root);
        for (AccessibilityNodeInfo node : nodes) {
            CharSequence text = node.getText();
            CharSequence desc = node.getContentDescription();
            String combined = ((text != null ? text.toString() : "") +
                               " " +
                               (desc != null ? desc.toString() : "")).toLowerCase().trim();

            for (String label : COPY_LINK_LABELS) {
                if (combined.contains(label.toLowerCase())) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);

                    // Read clipboard after a short delay
                    mainHandler.postDelayed(() -> {
                        String url = getClipboardUrl();
                        if (url != null && !url.equals(lastAnalyzedUrl)) {
                            sendToOverlay(url);
                        }
                        // Close share sheet
                        performGlobalAction(GLOBAL_ACTION_BACK);
                    }, 600);

                    recycleAll(nodes);
                    root.recycle();
                    return;
                }
            }
        }

        recycleAll(nodes);
        root.recycle();

        // If we couldn't find copy link, close sheet and try clipboard
        performGlobalAction(GLOBAL_ACTION_BACK);
        mainHandler.postDelayed(() -> {
            String url = getClipboardUrl();
            if (url != null && !url.equals(lastAnalyzedUrl)) {
                sendToOverlay(url);
            }
        }, 400);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    private AccessibilityNodeInfo findShareButton(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> nodes = getAllNodes(root);
        AccessibilityNodeInfo result = null;

        for (AccessibilityNodeInfo node : nodes) {
            if (!node.isClickable()) continue;
            CharSequence text = node.getText();
            CharSequence desc = node.getContentDescription();
            String combined = ((text != null ? text.toString() : "") +
                               " " +
                               (desc != null ? desc.toString() : "")).toLowerCase();

            for (String label : SHARE_LABELS) {
                if (combined.contains(label.toLowerCase())) {
                    // Prefer exact "share" match to avoid false positives
                    if (result == null) result = node;
                }
            }
        }

        // Recycle all except result
        for (AccessibilityNodeInfo node : nodes) {
            if (node != result) node.recycle();
        }

        return result;
    }

    private List<AccessibilityNodeInfo> getAllNodes(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> result = new ArrayList<>();
        if (root == null) return result;
        collectNodes(root, result);
        return result;
    }

    private void collectNodes(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> result) {
        if (node == null) return;
        result.add(node);
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) collectNodes(child, result);
        }
    }

    private void recycleAll(List<AccessibilityNodeInfo> nodes) {
        for (AccessibilityNodeInfo n : nodes) {
            try { n.recycle(); } catch (Exception ignored) {}
        }
    }

    private String getClipboardUrl() {
        try {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm == null || !cm.hasPrimaryClip()) return null;
            String text = cm.getPrimaryClip().getItemAt(0).coerceToText(this).toString().trim();
            if (text.startsWith("http") && VIDEO_URL_PATTERN.matcher(text).find()) {
                return text;
            }
        } catch (Exception ignored) {}
        return null;
    }

    private void sendToOverlay(String url) {
        lastAnalyzedUrl = url;
        // Send to OverlayService via intent
        Intent intent = new Intent(this, OverlayService.class);
        intent.setAction("DETECT_URL");
        intent.putExtra("url", url);
        startForegroundService(intent);
    }

    @Override
    public void onInterrupt() {}
}
