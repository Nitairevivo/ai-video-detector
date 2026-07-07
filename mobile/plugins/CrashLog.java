package com.verifai.app;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Date;

/**
 * Persists native crashes to a file the JS side reads and shows on next launch.
 * Lets us diagnose crashes on devices without USB debugging.
 */
public final class CrashLog {

    private static final long MAX_SIZE = 100 * 1024; // stop growing past 100KB

    private CrashLog() {}

    public static void log(Context ctx, String where, Throwable t) {
        try {
            File f = new File(ctx.getFilesDir(), "verifai_crash.txt");
            if (f.exists() && f.length() > MAX_SIZE) return;
            try (PrintWriter pw = new PrintWriter(new FileWriter(f, true))) {
                pw.println("[" + new Date() + "] " + where);
                pw.println(Log.getStackTraceString(t));
                pw.println("----");
            }
        } catch (Exception ignored) {}
        Log.e("VerifAI", "Crash in " + where, t);
    }
}
