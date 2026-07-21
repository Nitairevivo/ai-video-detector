package com.verifai.app;

import java.util.List;

/**
 * Lab: compiles and runs the REAL DetectionPolicy (the shipped Java the
 * floating button delegates to) with plain javac — no emulator. This is as
 * close to "testing the phone code" as we can get without a device.
 */
public class DetectionPolicyTest {
    static int failed = 0;
    static void check(String name, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + name);
        if (!cond) failed++;
    }

    public static void main(String[] args) {
        // ── Freemium daily quota ──
        DetectionPolicy.Quota q1 = DetectionPolicy.quota(false, 3, "2026-07-20", "2026-07-20", 0);
        check("free 1st check allowed, count->1", q1.allow && q1.newCount == 1 && !q1.paywall);
        DetectionPolicy.Quota q3 = DetectionPolicy.quota(false, 3, "2026-07-20", "2026-07-20", 3);
        check("free 4th check -> paywall (no run)", !q3.allow && q3.paywall);
        DetectionPolicy.Quota qNew = DetectionPolicy.quota(false, 3, "2026-07-21", "2026-07-20", 3);
        check("new day resets the counter", qNew.allow && qNew.newCount == 1 && !qNew.paywall);
        DetectionPolicy.Quota qPro = DetectionPolicy.quota(true, 3, "2026-07-20", "2026-07-20", 999);
        check("pro is unlimited, never paywall", qPro.allow && !qPro.paywall);

        // ── Cancel refund ──
        check("cancel refunds one within the day", DetectionPolicy.refund(false, "d", "d", 2) == 1);
        check("refund never goes below zero", DetectionPolicy.refund(false, "d", "d", 0) == 0);
        check("no refund across a day boundary", DetectionPolicy.refund(false, "d2", "d", 2) == 2);
        check("no refund for pro", DetectionPolicy.refund(true, "d", "d", 2) == 2);

        // ── The WhatsApp/Telegram screen-record bug: never screen silently ──
        check("no file access -> PROMPT (not screen)",
            DetectionPolicy.fileUnavailable(false).equals(DetectionPolicy.PROMPT_ACCESS));
        check("access granted but no saved file -> screen frames",
            DetectionPolicy.fileUnavailable(true).equals(DetectionPolicy.SCREEN));

        // ── Folder lists ──
        List<String> wa = DetectionPolicy.appVideoDirs("/sd", "com.whatsapp");
        check("whatsapp -> Android/media video folder",
            wa.contains("/sd/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video"));
        List<String> tg = DetectionPolicy.appVideoDirs("/sd", "org.telegram.messenger");
        check("telegram -> Android/media video folder",
            tg.contains("/sd/Android/media/org.telegram.messenger/Telegram/Telegram Video"));
        check("unknown app -> no folders", DetectionPolicy.appVideoDirs("/sd", "com.youtube").isEmpty());
        check("null package -> no folders (no NPE)", DetectionPolicy.appVideoDirs("/sd", null).isEmpty());

        // ── Link parsing: a bug here means a YouTube link never resolves ──
        check("watch?v= id", "dQw4w9WgXcQ".equals(DetectionPolicy.youtubeVideoId("https://www.youtube.com/watch?v=dQw4w9WgXcQ")));
        check("youtu.be/ id", "dQw4w9WgXcQ".equals(DetectionPolicy.youtubeVideoId("https://youtu.be/dQw4w9WgXcQ?t=5")));
        check("/shorts/ id", "abcDEF12345".equals(DetectionPolicy.youtubeVideoId("https://youtube.com/shorts/abcDEF12345")));
        check("/embed/ id", "abcDEF12345".equals(DetectionPolicy.youtubeVideoId("https://www.youtube.com/embed/abcDEF12345")));
        check("watch?v= with extra params", "abcDEF12345".equals(DetectionPolicy.youtubeVideoId("https://m.youtube.com/watch?feature=x&v=abcDEF12345&t=1")));
        check("non-YouTube URL -> null", DetectionPolicy.youtubeVideoId("https://tiktok.com/@u/video/123") == null);
        check("null URL -> null (no NPE)", DetectionPolicy.youtubeVideoId(null) == null);

        if (failed > 0) { System.out.println("\nJAVA-POLICY: " + failed + " test(s) FAILED"); System.exit(1); }
        System.out.println("JAVA-POLICY: all real-Java policy tests passed");
    }
}
