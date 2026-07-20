package com.verifai.app;

import java.util.ArrayList;
import java.util.List;

/**
 * Pure, Android-free detection/billing policy.
 *
 * The logic that has actually broken in the field (freemium counting, the
 * "prompt for file access vs silently screen-record" decision, and the exact
 * WhatsApp/Telegram folder list) lives HERE, with no Android imports, so the
 * lab can compile and unit-test it with plain javac — no emulator. OverlayService
 * and OverlayModule delegate to it, so the tested logic IS the shipped logic.
 */
public final class DetectionPolicy {
    private DetectionPolicy() {}

    // ── Freemium daily quota ──────────────────────────────────────────────
    public static final class Quota {
        public final boolean allow;    // may this tap run a detection?
        public final int newCount;     // value to persist as quota_count
        public final boolean paywall;  // show the upgrade screen?
        Quota(boolean allow, int newCount, boolean paywall) {
            this.allow = allow; this.newCount = newCount; this.paywall = paywall;
        }
    }

    /** Pro users are unlimited. Free users get {@code limit} checks per calendar
     *  day; the counter resets on a new day. Returns whether this tap may run and
     *  the counter value to persist. */
    public static Quota quota(boolean pro, int limit, String today, String storedDay, int storedCount) {
        if (pro) return new Quota(true, storedCount, false);
        int count = today.equals(storedDay) ? storedCount : 0;
        if (count >= limit) return new Quota(false, count, true);
        return new Quota(true, count + 1, false);
    }

    /** Give back one check that was counted at tap time but produced no verdict
     *  (e.g. cancel). Never below zero, and only for the current day. */
    public static int refund(boolean pro, String today, String storedDay, int storedCount) {
        if (pro || !today.equals(storedDay)) return storedCount;
        return Math.max(0, storedCount - 1);
    }

    // ── File-unavailable fallback ─────────────────────────────────────────
    public static final String PROMPT_ACCESS = "prompt_access";
    public static final String SCREEN = "screen";

    /** When no readable local file could be obtained: if the blocker is the
     *  missing All-Files-Access permission, ask for it; only when access IS
     *  granted (so the file genuinely isn't saved to a readable folder) do we
     *  fall back to reading the on-screen frames. This is the guarantee that
     *  fixed "WhatsApp/Telegram screen-records instead of reading the code". */
    public static String fileUnavailable(boolean hasAllFilesAccess) {
        return hasAllFilesAccess ? SCREEN : PROMPT_ACCESS;
    }

    // ── WhatsApp / Telegram saved-video folders ───────────────────────────
    /** The exact public folders WhatsApp/Telegram write received videos to.
     *  Scanned directly (File API) because WhatsApp's .nomedia keeps them out
     *  of MediaStore. {@code ext} is the external-storage root. */
    public static List<String> appVideoDirs(String ext, String pkg) {
        List<String> d = new ArrayList<>();
        if (pkg == null) return d;
        if (pkg.contains("telegram") || pkg.contains("challegram")) {
            d.add(ext + "/Android/media/org.telegram.messenger/Telegram/Telegram Video");
            d.add(ext + "/Android/media/org.telegram.messenger.web/Telegram/Telegram Video");
            d.add(ext + "/Telegram/Telegram Video");
            d.add(ext + "/Android/media/org.telegram.plus/Telegram/Telegram Video");
        } else if (pkg.contains("whatsapp")) {
            d.add(ext + "/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video");
            d.add(ext + "/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video/Sent");
            d.add(ext + "/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Video");
            d.add(ext + "/WhatsApp/Media/WhatsApp Video");
        }
        return d;
    }
}
