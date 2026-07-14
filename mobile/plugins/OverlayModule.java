package com.verifai.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.ContextCompat;

import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;

public class OverlayModule extends ReactContextBaseJavaModule {

    private final ReactApplicationContext reactContext;

    public OverlayModule(ReactApplicationContext ctx) {
        super(ctx);
        this.reactContext = ctx;
    }

    @Override
    public String getName() { return "OverlayModule"; }

    @ReactMethod
    public void hasPermission(Promise promise) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            promise.resolve(Settings.canDrawOverlays(reactContext));
        } else {
            promise.resolve(true);
        }
    }

    @ReactMethod
    public void requestPermission(Promise promise) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(reactContext)) {
                Intent intent = new Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + reactContext.getPackageName())
                );
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                reactContext.startActivity(intent);
                promise.resolve(false); // will need to check again after user returns
                return;
            }
        }
        promise.resolve(true);
    }

    @ReactMethod
    public void start(Promise promise) {
        try {
            // NOTE: we deliberately do NOT gate on Settings.canDrawOverlays()
            // here. On many OEM skins (MIUI, ColorOS, One UI…) that flag reads
            // false even when the user HAS granted "display over other apps",
            // which used to trap the user in an endless "grant permission" loop.
            // Instead we just try to start the service; OverlayService attempts
            // to add the view and the JS side confirms success via serviceRunning
            // — trusting what actually happens, not the unreliable flag.
            Intent intent = new Intent(reactContext, OverlayService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                reactContext.startForegroundService(intent);
            } else {
                reactContext.startService(intent);
            }
            promise.resolve(true);
        } catch (Exception e) {
            promise.reject("START_ERROR", e.getMessage());
        }
    }

    @ReactMethod
    public void stop(Promise promise) {
        try {
            reactContext.stopService(new Intent(reactContext, OverlayService.class));
            promise.resolve(true);
        } catch (Exception e) {
            promise.reject("STOP_ERROR", e.getMessage());
        }
    }

    @ReactMethod
    public void isRunning(Promise promise) {
        // The service keeps a same-process instance handle — this is the truth,
        // not a guess, so the JS switch never drifts out of sync.
        promise.resolve(OverlayService.instance != null);
    }

    /** One call the JS status card uses to show live diagnostics:
     *  overlay permission / accessibility service / floating service state. */
    @ReactMethod
    public void getStatus(Promise promise) {
        try {
            com.facebook.react.bridge.WritableMap map = com.facebook.react.bridge.Arguments.createMap();
            // If the button service is running, the overlay demonstrably works —
            // report the permission as granted even when canDrawOverlays() lies
            // (OEM skins), so the status row shows green and stops nagging.
            boolean overlayPerm = Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || Settings.canDrawOverlays(reactContext)
                || OverlayService.instance != null;
            map.putBoolean("overlayPermission", overlayPerm);
            map.putBoolean("serviceRunning", OverlayService.instance != null);
            String enabled = Settings.Secure.getString(
                reactContext.getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            String pkg = reactContext.getPackageName();
            boolean acc = enabled != null &&
                (enabled.contains(pkg + "/" + VerifAIAccessibilityService.class.getName())
                 || enabled.contains(pkg + "/.VerifAIAccessibilityService"));
            map.putBoolean("accessibilityEnabled", acc);
            promise.resolve(map);
        } catch (Exception e) {
            promise.reject("STATUS_ERROR", e.getMessage());
        }
    }

    @ReactMethod
    public void isAccessibilityEnabled(Promise promise) {
        try {
            String enabled = Settings.Secure.getString(
                reactContext.getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            String pkg = reactContext.getPackageName();
            boolean on = enabled != null &&
                (enabled.contains(pkg + "/" + VerifAIAccessibilityService.class.getName())
                 || enabled.contains(pkg + "/.VerifAIAccessibilityService"));
            promise.resolve(on);
        } catch (Exception e) {
            promise.resolve(false);
        }
    }

    @ReactMethod
    public void openAccessibilitySettings(Promise promise) {
        try {
            Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            reactContext.startActivity(intent);
            promise.resolve(true);
        } catch (Exception e) {
            promise.reject("OPEN_SETTINGS_ERROR", e.getMessage());
        }
    }
}
