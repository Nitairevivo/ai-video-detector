package com.verifai.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

/**
 * Captures ONE frame of the screen via MediaProjection, encodes it to JPEG, and
 * hands it to {@link OverlayService} for /detect-frame analysis. This is the
 * last-resort fallback used when neither the clipboard nor the accessibility
 * Share→Copy-Link automation could produce a video URL (e.g. SSL-pinned apps).
 *
 * Runs as a foreground service of type mediaProjection, which Android 14+
 * requires to be started *before* MediaProjection.getMediaProjection() is used.
 */
public class ScreenCaptureService extends Service {

    public static final String EXTRA_RESULT_CODE = "resultCode";
    public static final String EXTRA_RESULT_DATA = "resultData";

    private static final String CHANNEL_ID = "verifai_capture";
    private static final int NOTIF_ID = 4712;
    private static final int MAX_EDGE = 1280;       // downscale long edge before upload
    private static final long CAPTURE_TIMEOUT_MS = 4000;

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private volatile boolean captured = false;

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Must enter the foreground (as mediaProjection) before touching the token.
        startForegroundNotification();

        if (intent == null) { finishWithFailure("no start intent"); return START_NOT_STICKY; }
        int code = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent data = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        if (data == null) { finishWithFailure("no projection grant"); return START_NOT_STICKY; }

        try {
            beginCapture(code, data);
        } catch (Exception e) {
            finishWithFailure(String.valueOf(e.getMessage()));
        }
        return START_NOT_STICKY;
    }

    private void beginCapture(int code, Intent data) {
        MediaProjectionManager mpm =
            (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        projection = mpm.getMediaProjection(code, data);
        if (projection == null) { finishWithFailure("null projection"); return; }

        // Required on newer APIs: a callback must be registered before capture.
        projection.registerCallback(new MediaProjection.Callback() {
            @Override public void onStop() {}
        }, handler);

        DisplayMetrics metrics = new DisplayMetrics();
        WindowManager wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        wm.getDefaultDisplay().getRealMetrics(metrics);
        final int w = metrics.widthPixels;
        final int h = metrics.heightPixels;
        final int dpi = metrics.densityDpi;

        imageReader = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2);
        virtualDisplay = projection.createVirtualDisplay(
            "verifai-capture", w, h, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.getSurface(), null, handler);

        imageReader.setOnImageAvailableListener(reader -> {
            if (captured) return;
            Image image = null;
            try {
                image = reader.acquireLatestImage();
                if (image == null) return;
                captured = true;
                byte[] jpeg = toJpeg(image, w, h);
                cleanup();
                OverlayService.onFrameCaptured(jpeg);
                stopSelf();
            } catch (Exception e) {
                finishWithFailure(String.valueOf(e.getMessage()));
            } finally {
                if (image != null) {
                    try { image.close(); } catch (Exception ignored) {}
                }
            }
        }, handler);

        // Safety net: if no frame arrives, don't hang the projection open.
        handler.postDelayed(() -> {
            if (!captured) finishWithFailure("capture timeout");
        }, CAPTURE_TIMEOUT_MS);
    }

    /** Convert a MediaProjection RGBA_8888 Image to a downscaled JPEG byte[]. */
    private byte[] toJpeg(Image image, int w, int h) {
        Image.Plane[] planes = image.getPlanes();
        ByteBuffer buffer = planes[0].getBuffer();
        int pixelStride = planes[0].getPixelStride();
        int rowStride = planes[0].getRowStride();
        int rowPadding = rowStride - pixelStride * w;

        // ImageReader rows may be padded — allocate padded width, then crop.
        Bitmap padded = Bitmap.createBitmap(
            w + rowPadding / pixelStride, h, Bitmap.Config.ARGB_8888);
        padded.copyPixelsFromBuffer(buffer);
        Bitmap frame = Bitmap.createBitmap(padded, 0, 0, w, h);
        if (frame != padded) padded.recycle();

        int longEdge = Math.max(w, h);
        if (longEdge > MAX_EDGE) {
            float scale = (float) MAX_EDGE / longEdge;
            Bitmap scaled = Bitmap.createScaledBitmap(
                frame, Math.round(w * scale), Math.round(h * scale), true);
            if (scaled != frame) frame.recycle();
            frame = scaled;
        }

        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        frame.compress(Bitmap.CompressFormat.JPEG, 80, baos);
        frame.recycle();
        return baos.toByteArray();
    }

    private void finishWithFailure(String reason) {
        cleanup();
        OverlayService.onFrameCaptureFailed(reason);
        stopSelf();
    }

    private void cleanup() {
        try { if (virtualDisplay != null) virtualDisplay.release(); } catch (Exception ignored) {}
        try { if (imageReader != null) imageReader.close(); } catch (Exception ignored) {}
        try { if (projection != null) projection.stop(); } catch (Exception ignored) {}
        virtualDisplay = null;
        imageReader = null;
        projection = null;
    }

    private void startForegroundNotification() {
        NotificationManager nm =
            (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "VerifAI Screen Check", NotificationManager.IMPORTANCE_MIN);
            if (nm != null) nm.createNotificationChannel(ch);
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        Notification notif = b
            .setContentTitle("VerifAI")
            .setContentText("בודק את המסך…")
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .build();

        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(NOTIF_ID, notif);
        }
    }

    @Override
    public void onDestroy() {
        cleanup();
        super.onDestroy();
    }
}
