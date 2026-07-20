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

    /** Persist the user's Pro entitlement so the native floating button knows
     *  whether to enforce the free daily limit. Called by JS after a purchase
     *  or an entitlement re-check. Stored in the same prefs the OverlayService
     *  reads. */
    @ReactMethod
    public void setProStatus(boolean isPro, Promise promise) {
        try {
            reactContext.getSharedPreferences("verifai_overlay", android.content.Context.MODE_PRIVATE)
                .edit().putBoolean("pro", isPro).apply();
            promise.resolve(true);
        } catch (Exception e) {
            promise.reject("ERR_SET_PRO", e);
        }
    }

    /** Override how many free checks per day the floating button allows before
     *  the paywall (default 3). Lets pricing be tuned without a native rebuild. */
    @ReactMethod
    public void setFreeDailyLimit(int limit, Promise promise) {
        try {
            reactContext.getSharedPreferences("verifai_overlay", android.content.Context.MODE_PRIVATE)
                .edit().putInt("free_daily_limit", Math.max(0, limit)).apply();
            promise.resolve(true);
        } catch (Exception e) {
            promise.reject("ERR_SET_LIMIT", e);
        }
    }

    /** How many free checks remain today (for showing "2/3 left" in the app).
     *  Returns a large number when Pro. */
    @ReactMethod
    public void freeChecksRemaining(Promise promise) {
        try {
            android.content.SharedPreferences p = reactContext.getSharedPreferences(
                "verifai_overlay", android.content.Context.MODE_PRIVATE);
            if (p.getBoolean("pro", false)) { promise.resolve(999999); return; }
            int limit = p.getInt("free_daily_limit", 3);
            String today = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
                .format(new java.util.Date());
            int count = today.equals(p.getString("quota_day", "")) ? p.getInt("quota_count", 0) : 0;
            promise.resolve(Math.max(0, limit - count));
        } catch (Exception e) {
            promise.reject("ERR_REMAINING", e);
        }
    }

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

    /** Ask the OS to exempt us from battery optimization. On aggressive OEMs
     *  this is what stops the overlay foreground service from being killed a
     *  few seconds after it starts. No-op if already exempt. */
    /** All-Files-Access is what lets the floating button READ the actual
     *  WhatsApp/Telegram video file (its code) on Android 11+. Without it the
     *  folder scan returns nothing and the app can only screen-record. */
    @ReactMethod
    public void hasAllFilesAccess(Promise promise) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try { promise.resolve(android.os.Environment.isExternalStorageManager()); }
            catch (Exception e) { promise.resolve(false); }
        } else {
            promise.resolve(true);
        }
    }

    @ReactMethod
    public void requestAllFilesAccess(Promise promise) {
        try {
            Intent i;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                i = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + reactContext.getPackageName()));
            } else {
                i = reactContext.getPackageManager()
                    .getLaunchIntentForPackage(reactContext.getPackageName());
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            reactContext.startActivity(i);
            promise.resolve(true);
        } catch (Exception e) {
            try {
                Intent i2 = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                i2.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                reactContext.startActivity(i2);
                promise.resolve(true);
            } catch (Exception e2) { promise.reject("ERR_ALLFILES", e2); }
        }
    }

    @ReactMethod
    public void requestIgnoreBatteryOptimizations(Promise promise) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                String pkg = reactContext.getPackageName();
                android.os.PowerManager pm = (android.os.PowerManager)
                    reactContext.getSystemService(android.content.Context.POWER_SERVICE);
                if (pm != null && !pm.isIgnoringBatteryOptimizations(pkg)) {
                    Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                    i.setData(Uri.parse("package:" + pkg));
                    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    reactContext.startActivity(i);
                    promise.resolve(false);   // asked; user must confirm
                    return;
                }
            }
            promise.resolve(true);            // already exempt / not needed
        } catch (Exception e) {
            promise.resolve(false);
        }
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

    /** Open the OEM "Autostart" / background-launch manager. On MIUI/HyperOS,
     *  ColorOS, Vivo, etc. the system kills the accessibility service (and the
     *  overlay) seconds after it starts UNLESS the app is allowed to autostart.
     *  This is the single most important permission to stop "accessibility
     *  disconnects by itself". Tries each OEM's hidden screen, and falls back to
     *  the app-details page (where Autostart usually also lives). */
    @ReactMethod
    public void openAutostartSettings(Promise promise) {
        String[][] targets = {
            // MIUI / Xiaomi / Redmi / POCO (HyperOS included)
            {"com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"},
            // ColorOS / Oppo / Realme
            {"com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"},
            {"com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"},
            {"com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"},
            // FuntouchOS / Vivo / iQOO
            {"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"},
            {"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"},
            // Huawei / Honor
            {"com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"},
            // Letv / OnePlus (older)
            {"com.letv.android.letvsafe", "com.letv.android.letvsafe.AutobootManageActivity"},
        };
        for (String[] t : targets) {
            try {
                Intent i = new Intent();
                i.setClassName(t[0], t[1]);
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                reactContext.startActivity(i);
                promise.resolve(true);
                return;
            } catch (Exception ignored) {
                // this OEM screen doesn't exist on this device — try the next
            }
        }
        // Fallback: the app-details screen (Autostart often listed there too).
        try {
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:" + reactContext.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            reactContext.startActivity(i);
            promise.resolve(false);   // opened, but not the exact autostart screen
        } catch (Exception e) {
            promise.resolve(false);
        }
    }
}
