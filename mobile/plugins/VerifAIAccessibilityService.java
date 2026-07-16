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
        "com.reddit.frontpage",        // Reddit
        "org.telegram.messenger",      // Telegram
        "org.telegram.messenger.web",  // Telegram (web/beta variant)
        "org.thunderdog.challegram",   // Telegram X
        "com.whatsapp",                // WhatsApp
        "com.whatsapp.w4b"             // WhatsApp Business
    ));

    /** Apps where the tapped video is a LOCAL downloaded file we can read the
     *  real code from, rather than a URL to fetch or a screen to photograph. */
    public static boolean isLocalFileApp(String pkg) {
        return pkg != null &&
            (pkg.contains("telegram") || pkg.contains("challegram") || pkg.contains("whatsapp"));
    }

    // Windows that must NOT change the button visibility (transient system UI,
    // share sheets, keyboards, and our own overlay/clipboard-reader windows).
    private static final Set<String> TRANSIENT_PACKAGES = new HashSet<>(Arrays.asList(
        "android",
        "com.android.systemui",
        "com.android.internal.app"
    ));

    // Share/copy button labels across languages
    private static final List<String> SHARE_LABELS = Arrays.asList(
        "share", "שתף", "שיתוף", "לשתף", "共享", "分享", "partager", "teilen",
        "compartir", "send to", "שלח ל", "share to"
    );
    private static final List<String> COPY_LINK_LABELS = Arrays.asList(
        "copy link", "copy url", "copy the link", "share link",
        "העתק קישור", "העתק לינק", "העתק את הקישור", "העתקת קישור", "העתק כתובת",
        "复制链接", "复制", "copier le lien", "enlace"
    );
    // Broad fallbacks, tried only if none of the specific copy-link labels hit —
    // "copy"/"העתק" alone can match the wrong control, so they're last resort.
    private static final List<String> COPY_FALLBACK_LABELS = Arrays.asList(
        "copy", "העתק", "kopieren", "copiar"
    );

    private static volatile VerifAIAccessibilityService instance;
    private static volatile String foregroundPackage = null;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private boolean grabInProgress = false;
    private boolean waitingForShareSheet = false;
    /** Whether the current grab flow actually clicked "Copy Link" — lets the
     *  overlay distinguish a fresh link from stale clipboard leftovers. */
    private boolean automationClicked = false;
    private int copyTries = 0;
    private static final int MAX_COPY_TRIES = 12;          // ~4.8s of polling
    private static final long COPY_POLL_MS = 400;
    private static final long GRAB_WATCHDOG_MS = 9000;

    // If a grab flow ever dies mid-way (app killed the share sheet, event never
    // arrived…) this watchdog clears the flags so the NEXT tap still works —
    // otherwise grabInProgress stays true forever and every tap gets stuck.
    private final Runnable grabWatchdog = () -> {
        if (grabInProgress) {
            grabInProgress = false;
            waitingForShareSheet = false;
            finishGrab();
        }
    };

    public static String getForegroundPackage() { return foregroundPackage; }

    /** True when the accessibility service is actually connected and can report
     *  the foreground app — lets the overlay decide whether it may auto-hide the
     *  button outside supported apps (it can't guess the app without this). */
    public static boolean isConnected() { return instance != null; }

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

            // Share sheet opened as part of the grab flow — an event is a good
            // extra chance to click sooner. This does NOT consume the poll's
            // retry budget or start a new timer chain (only the poll does that).
            if (waitingForShareSheet) attemptCopyLink();
        }

        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED && waitingForShareSheet) {
            attemptCopyLink();
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
        automationClicked = false;
        mainHandler.removeCallbacks(grabWatchdog);
        mainHandler.postDelayed(grabWatchdog, GRAB_WATCHDOG_MS);

        AccessibilityNodeInfo root = getRootInActiveWindow();
        AccessibilityNodeInfo shareBtn = root != null ? findShareButton(root) : null;

        if (shareBtn == null) {
            // findShareButton already recycled every node INCLUDING root (it
            // recycles all nodes except the non-null result). Do NOT recycle
            // root again — a double recycle throws on API < 33.
            finishGrab();
            return;
        }

        waitingForShareSheet = true;
        copyTries = 0;
        shareBtn.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        shareBtn.recycle();
        // (root was already recycled inside findShareButton — don't touch it.)

        // Poll for the "Copy link" row — the share sheet animates in and its
        // contents change, so a single look almost always misses it. The POLL
        // owns the retry budget (~5s) and rescheduling; window events only get
        // extra immediate attempts via attemptCopyLink(). Scrolls the sheet
        // halfway through in case Copy link is off-screen.
        mainHandler.postDelayed(this::pollCopyLink, COPY_POLL_MS);
    }

    /** The timer chain: one attempt, then reschedule until the budget runs out.
     *  Only THIS increments copyTries / reschedules — so a burst of share-sheet
     *  content-changed events can't exhaust the budget before the row renders. */
    private void pollCopyLink() {
        if (!waitingForShareSheet) return;
        attemptCopyLink();
        if (!waitingForShareSheet) return;   // clicked → done
        if (++copyTries < MAX_COPY_TRIES) {
            mainHandler.postDelayed(this::pollCopyLink, COPY_POLL_MS);
        } else {
            waitingForShareSheet = false;
            closeSheetAndFinish();           // give up → clipboard may still help
        }
    }

    /** One look at the current window for the "Copy link" row (specific labels
     *  first, broad "copy" only after a few tries, scroll at try 5). Does NOT
     *  touch copyTries or reschedule — safe to call from both the poll and window
     *  events. recycleAll() recycles root too (it's node 0), so there is no bare
     *  root.recycle() that could double-recycle and crash on API < 33. */
    private void attemptCopyLink() {
        if (!waitingForShareSheet) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        List<AccessibilityNodeInfo> nodes = getAllNodes(root);
        try {
            if (clickFirstMatch(nodes, COPY_LINK_LABELS)) return;
            if (copyTries >= 4 && clickFirstMatch(nodes, COPY_FALLBACK_LABELS)) return;
            if (copyTries == 5) scrollAnyScrollable(nodes);
        } finally {
            recycleAll(nodes);
        }
    }

    /** Click the first clickable node whose text/desc contains any label.
     *  Returns true and finishes the grab (via clipboard read) if it clicked. */
    private boolean clickFirstMatch(List<AccessibilityNodeInfo> nodes, List<String> labels) {
        for (AccessibilityNodeInfo node : nodes) {
            if (node == null) continue;
            CharSequence text = node.getText();
            CharSequence desc = node.getContentDescription();
            String combined = ((text != null ? text.toString() : "") + " " +
                               (desc != null ? desc.toString() : "")).toLowerCase().trim();
            if (combined.isEmpty()) continue;
            for (String label : labels) {
                if (combined.contains(label.toLowerCase())) {
                    AccessibilityNodeInfo target = clickableSelfOrAncestor(node);
                    automationClicked = true;
                    waitingForShareSheet = false;
                    if (target != null) target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    // Let the app write the clipboard, then close + read it.
                    mainHandler.postDelayed(this::closeSheetAndFinish, 650);
                    return true;
                }
            }
        }
        return false;
    }

    /** The label node itself is often not the clickable one — walk up to the
     *  nearest clickable ancestor so the tap registers. */
    private AccessibilityNodeInfo clickableSelfOrAncestor(AccessibilityNodeInfo n) {
        AccessibilityNodeInfo cur = n;
        for (int i = 0; i < 5 && cur != null; i++) {
            if (cur.isClickable()) return cur;
            cur = cur.getParent();
        }
        return n;
    }

    /** Scroll the first scrollable node forward (reveals an off-screen row). */
    private void scrollAnyScrollable(List<AccessibilityNodeInfo> nodes) {
        for (AccessibilityNodeInfo node : nodes) {
            if (node != null && node.isScrollable()) {
                node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                return;
            }
        }
    }

    private void closeSheetAndFinish() {
        performGlobalAction(GLOBAL_ACTION_BACK);
        mainHandler.postDelayed(this::finishGrab, 350);
    }

    private void finishGrab() {
        grabInProgress = false;
        waitingForShareSheet = false;
        mainHandler.removeCallbacks(grabWatchdog);
        // Read the clipboard through the focused transparent activity
        // (background clipboard reads are blocked on Android 10+).
        try {
            Intent i = new Intent(this, ClipboardReaderActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION);
            i.putExtra(ClipboardReaderActivity.EXTRA_SOURCE, OverlayService.SOURCE_AUTOMATION);
            i.putExtra(OverlayService.EXTRA_AUTOMATION_CLICKED, automationClicked);
            startActivity(i);
        } catch (Exception e) {
            // The overlay is waiting for a callback — never leave it hanging.
            OverlayService.onAutomationFailed();
        }
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
