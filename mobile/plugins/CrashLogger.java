package com.verifai.app;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.PrintWriter;
import java.io.StringWriter;

public class CrashLogger {
    private static final String PREFS = "verifai_crash";
    private static final String KEY = "last_crash";

    public static void init(Context ctx) {
        Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            try {
                StringWriter sw = new StringWriter();
                throwable.printStackTrace(new PrintWriter(sw));
                String msg = "Thread: " + thread.getName() + "\n" + sw;
                ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                   .edit().putString(KEY, msg).commit();
            } catch (Exception ignored) {}
            if (prev != null) prev.uncaughtException(thread, throwable);
        });
    }

    public static String getAndClear(Context ctx) {
        SharedPreferences prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String crash = prefs.getString(KEY, null);
        if (crash != null) prefs.edit().remove(KEY).commit();
        return crash;
    }
}
