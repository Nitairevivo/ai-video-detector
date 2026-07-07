package com.verifai.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
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

public class VerifAIAccessibilityService extends AccessibilityService {

    /** Apps where the floating button is allowed to appear. */
    public static final Set<String> SUPPORTED_PACKAGES = new HashSet<>(Arrays.asList(
        "com.zhiliaoapp.musically",   // TikTok
        "com.ss.android.ugc.trill",   // TikTok (some regions)
        "com.instagram.android",       // Instagram
        "com.google.android.youtube",  // YouTube
        "com.facebook.katana",         // Facebook
        "com.twitter.android",         // Twitter/X
        "com.reddit.frontpage"         // Reddit
    ));

    // Windows that must NOT change the button visibility (transient system UI,
    // share sheets, keyboards, and our own overlay/clipboard-reader windows).
    private static final Set<String> TRANSIENT_PACKAGES = new HashSet<>(Arrays.asList(
        "android",
        "com.android.systemui",
        "com.android.internal.app"
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

    private static volatile VerifAIAccessibilityService instance;
    private static volatile String foregroundPackage = null;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private boolean grabInProgress = false;
    private boolean waitingForShareSheet = false;
    private static final long SHARE_SHEET_TIMEOUT_MS = 2500;

    public static String getForegroundPackage() { return foregroundPackage; }

    /**
     * Called by OverlayService when the floating button is tapped and the
     * clipboard has no fresh link. Clicks Share → Copy Link in the current app,
     * then hands off to ClipboardReaderActivity, which reports back to
     * OverlayService (ACTION_CLIPBOARD_RESULT / source=automation).
     * Returns false when the accessibility service isn't running or the
     * foreground app isn't supported — the caller then shows guidance instead.
     */
    public static boolean grabCurrentVideoUrl() {
        VerifAIAccessibilityService s = instance;
        if (s == null) return false;
        String fg = foregroundPackage;
        if (fg == null || !SUPPORTED_PACKAGES.contains(fg)) return false;
        s.mainHandler.post(s::startGrabFlow);
        return true;
    }

    @Override
    protected void onServiceConnected() {
        instance = this;
        try {
            configureAndStart();
        } catch (Throwable t) {
            CrashLog.log(this, "VerifAIAccessibilityService.onServiceConnected", t);
        }
    }

    private void configureAndStart() {
        AccessibilityServiceInfo info = new AccessibilityServiceInfo();
        info.eventTypes =
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED;
        // No package filter: we must see every app to know when to HIDE the button
        info.packageNames = null;
        info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
        info.notificationTimeout = 100;
        info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
                     AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        setServiceInfo(info);

        // Do NOT start the overlay foreground service from here. This runs in the
        // background, and starting a specialUse FGS from the background crashes
        // the process on Android 14+ (uncatchable framework exception). The user
        // starts the overlay from the home-screen toggle (foreground = allowed);
        // once running, this service only drives button visibility via
        // OverlayService.notifyForegroundApp().
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        try {
            handleEvent(event);
        } catch (Throwable t) {
            CrashLog.log(this, "VerifAIAccessibilityService.onAccessibilityEvent", t);
        }
    }

    private void handleEvent(AccessibilityEvent event) {
        String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";
        int type = event.getEventType();

        // ── Track the foreground app → show/hide the floating button ─────────
        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            if (!pkg.isEmpty() && !isTransient(pkg)) {
                foregroundPackage = pkg;
                OverlayService.notifyForegroundApp(pkg);
            }

            // Share sheet opened as part of the grab flow
            if (waitingForShareSheet) {
                mainHandler.postDelayed(this::findAndClickCopyLink, 400);
            }
        }

        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED && waitingForShareSheet) {
            findAndClickCopyLink();
        }
    }

    private boolean isTransient(String pkg) {
        if (TRANSIENT_PACKAGES.contains(pkg)) return true;
        if (pkg.equals(getPackageName())) return true;      // our own overlay / clipboard reader
        if (pkg.contains("inputmethod")) return true;        // keyboards
        return false;
    }

    // ─── Grab flow: Share → Copy Link → ClipboardReaderActivity ──────────────

    private void startGrabFlow() {
        if (grabInProgress) return;
        grabInProgress = true;

        AccessibilityNodeInfo root = getRootInActiveWindow();
        AccessibilityNodeInfo shareBtn = root != null ? findShareButton(root) : null;

        if (shareBtn == null) {
            if (root != null) root.recycle();
            // Can't find a Share button — maybe the clipboard still helps
            finishGrab();
            return;
        }

        waitingForShareSheet = true;
        shareBtn.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        shareBtn.recycle();
        if (root != null) root.recycle();

        // Fallback if the share sheet never opens
        mainHandler.postDelayed(() -> {
            if (waitingForShareSheet) findAndClickCopyLink();
        }, SHARE_SHEET_TIMEOUT_MS);
    }

    private void findAndClickCopyLink() {
        if (!waitingForShareSheet) return;
        waitingForShareSheet = false;

        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) { closeSheetAndFinish(); return; }

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
                    recycleAll(nodes);
                    root.recycle();
                    // Give the app a moment to write the clipboard, then close
                    // the sheet and read the clipboard via the transparent activity
                    mainHandler.postDelayed(this::closeSheetAndFinish, 600);
                    return;
                }
            }
        }

        recycleAll(nodes);
        root.recycle();
        closeSheetAndFinish();
    }

    private void closeSheetAndFinish() {
        performGlobalAction(GLOBAL_ACTION_BACK);
        mainHandler.postDelayed(this::finishGrab, 350);
    }

    private void finishGrab() {
        grabInProgress = false;
        waitingForShareSheet = false;
        // Read the clipboard through the focused transparent activity
        // (background clipboard reads are blocked on Android 10+).
        try {
            Intent i = new Intent(this, ClipboardReaderActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
            i.putExtra(ClipboardReaderActivity.EXTRA_SOURCE, OverlayService.SOURCE_AUTOMATION);
            startActivity(i);
        } catch (Exception ignored) {}
    }

    // ─── Node helpers ─────────────────────────────────────────────────────────

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

    @Override
    public boolean onUnbind(Intent intent) {
        instance = null;
        foregroundPackage = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        instance = null;
        foregroundPackage = null;
        super.onDestroy();
    }

    @Override
    public void onInterrupt() {}
}
