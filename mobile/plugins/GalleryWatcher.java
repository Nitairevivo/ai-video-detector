package com.verifai.app;

import android.content.Context;
import android.database.ContentObserver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashSet;
import java.util.Set;

import org.json.JSONObject;

/**
 * Watches the gallery for new videos.
 * When a video is saved (from TikTok, WhatsApp, etc.), automatically analyzes it.
 */
public class GalleryWatcher {

    private final Context context;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private ContentObserver observer;
    private final Set<String> analyzedPaths = new HashSet<>();

    // Callback when detection is complete
    public interface DetectionCallback {
        void onResult(String filePath, String verdict, float confidence, String method);
        void onError(String filePath, String error);
    }

    private DetectionCallback callback;

    public GalleryWatcher(Context context, DetectionCallback callback) {
        this.context = context;
        this.callback = callback;
    }

    public void start() {
        observer = new ContentObserver(new Handler()) {
            @Override
            public void onChange(boolean selfChange, Uri uri) {
                if (uri != null) {
                    handleNewMedia(uri);
                }
            }
        };
        context.getContentResolver().registerContentObserver(
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
            true,
            observer
        );
    }

    public void stop() {
        if (observer != null) {
            context.getContentResolver().unregisterContentObserver(observer);
            observer = null;
        }
    }

    private void handleNewMedia(Uri uri) {
        String[] projection = {
            MediaStore.Video.Media._ID,
            MediaStore.Video.Media.DATA,
            MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.DATE_ADDED,
            MediaStore.Video.Media.SIZE,
        };

        try (Cursor cursor = context.getContentResolver().query(
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                projection,
                MediaStore.Video.Media.DATE_ADDED + " > ?",
                new String[]{String.valueOf(System.currentTimeMillis() / 1000 - 5)},
                MediaStore.Video.Media.DATE_ADDED + " DESC"
        )) {
            if (cursor == null || !cursor.moveToFirst()) return;

            String path = cursor.getString(cursor.getColumnIndexOrThrow(MediaStore.Video.Media.DATA));
            long size = cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.Video.Media.SIZE));

            // Skip if already analyzed or too small
            if (path == null || analyzedPaths.contains(path) || size < 50000) return;
            analyzedPaths.add(path);

            // Analyze in background
            new Thread(() -> analyzeFile(path)).start();
        } catch (Exception ignored) {}
    }

    private void analyzeFile(String filePath) {
        try {
            File file = new File(filePath);
            if (!file.exists()) return;

            // Upload to /detect endpoint
            String boundary = "VerifAIGallery" + System.currentTimeMillis();
            URL apiUrl = new URL("https://ai-video-detector-production-a305.up.railway.app/detect");
            HttpURLConnection conn = (HttpURLConnection) apiUrl.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(30000);

            try (OutputStream out = conn.getOutputStream()) {
                String header = "--" + boundary + "\r\n" +
                    "Content-Disposition: form-data; name=\"file\"; filename=\"" + file.getName() + "\"\r\n" +
                    "Content-Type: video/mp4\r\n\r\n";
                out.write(header.getBytes("UTF-8"));

                try (FileInputStream fis = new FileInputStream(file)) {
                    byte[] buf = new byte[65536];
                    int n;
                    long total = 0;
                    while ((n = fis.read(buf)) != -1 && total < 20 * 1024 * 1024) {
                        out.write(buf, 0, n);
                        total += n;
                    }
                }
                out.write(("\r\n--" + boundary + "--\r\n").getBytes("UTF-8"));
            }

            if (conn.getResponseCode() == 200) {
                StringBuilder sb = new StringBuilder();
                try (java.io.BufferedReader br = new java.io.BufferedReader(
                        new java.io.InputStreamReader(conn.getInputStream()))) {
                    String line;
                    while ((line = br.readLine()) != null) sb.append(line);
                }
                JSONObject result = new JSONObject(sb.toString());
                String verdict = result.optString("verdict", "real");
                float confidence = (float) result.optDouble("confidence", 0.04);
                String method = result.optString("detection_method", "");

                mainHandler.post(() -> callback.onResult(filePath, verdict, confidence, method));
            }
        } catch (Exception e) {
            mainHandler.post(() -> callback.onError(filePath, e.getMessage()));
        }
    }
}
