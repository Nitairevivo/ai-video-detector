package com.verifai.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;

/**
 * Transparent, chromeless activity whose only job is to obtain screen-capture
 * consent. MediaProjection consent must come from an Activity result, so this
 * pops the system "Start recording or casting?" dialog, forwards the grant to
 * {@link ScreenCaptureService}, and immediately finishes.
 */
public class MediaProjectionRequestActivity extends Activity {

    private static final int REQ_CAPTURE = 4711;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        MediaProjectionManager mpm =
            (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        if (mpm == null) {
            fail("screen capture unavailable");
            finish();
            return;
        }
        try {
            startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAPTURE);
        } catch (Exception e) {
            fail(String.valueOf(e.getMessage()));
            finish();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_CAPTURE && resultCode == RESULT_OK && data != null) {
            Intent svc = new Intent(this, ScreenCaptureService.class);
            svc.putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode);
            svc.putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, data);
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(svc);
                } else {
                    startService(svc);
                }
            } catch (Exception e) {
                fail(String.valueOf(e.getMessage()));
            }
        } else {
            fail("הרשאת צילום מסך נדחתה");
        }
        finish();
    }

    private void fail(String reason) {
        OverlayService.onFrameCaptureFailed(reason);
    }
}
