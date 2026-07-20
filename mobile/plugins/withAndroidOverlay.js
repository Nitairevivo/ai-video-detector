const {
  withAndroidManifest,
  withDangerousMod,
  withPlugins,
} = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

// ─── Paths to our Java source files (sibling to this plugin file) ───────────
const PLUGIN_DIR = __dirname;
const JAVA_DIR = PLUGIN_DIR;

// Google Play variant: Play policy rejects AccessibilityService-driven
// automation of other apps, so this build ships WITHOUT the accessibility
// service (no manifest entry) and the floating button analyzes via screen
// capture only. Set in eas.json (profile "play") so the same env var also
// reaches the JS bundle as an EXPO_PUBLIC_ constant.
const PLAY_BUILD = process.env.EXPO_PUBLIC_PLAY_BUILD === "1";

function withOverlayManifest(config) {
  return withAndroidManifest(config, (cfg) => {
    const manifest = cfg.modResults.manifest;

    // Add permissions
    if (!manifest["uses-permission"]) manifest["uses-permission"] = [];
    const existingPerms = manifest["uses-permission"].map(
      (p) => p.$["android:name"]
    );

    const neededPerms = [
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.FOREGROUND_SERVICE",
      "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
      "android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION",
      "android.permission.RECEIVE_BOOT_COMPLETED",
      // Aggressive OEMs (Xiaomi/MIUI, Oppo, Vivo) kill the overlay foreground
      // service seconds after it starts ("button appears then vanishes").
      // Exempting the app from battery optimization keeps it alive.
      "android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
      // Read the actual WhatsApp/Telegram video FILE (its code). On Android 11+
      // File-API access to another app's Android/media folder needs this.
      "android.permission.MANAGE_EXTERNAL_STORAGE",
    ];
    for (const perm of neededPerms) {
      if (!existingPerms.includes(perm)) {
        manifest["uses-permission"].push({ $: { "android:name": perm } });
      }
    }

    // Add services inside <application>
    const app = manifest.application[0];
    if (!app.service) app.service = [];
    const existingServices = app.service.map((s) => s.$["android:name"]);

    if (!existingServices.includes(".OverlayService")) {
      app.service.push({
        $: {
          "android:name": ".OverlayService",
          "android:exported": "false",
          "android:foregroundServiceType": "specialUse",
        },
        "property": [{
          $: {
            "android:name": "android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE",
            "android:value": "Draws a floating AI detection button over other apps",
          }
        }]
      });
    }

    // Screen-capture service (MediaProjection frame fallback)
    if (!existingServices.includes(".ScreenCaptureService")) {
      app.service.push({
        $: {
          "android:name": ".ScreenCaptureService",
          "android:exported": "false",
          "android:foregroundServiceType": "mediaProjection",
        },
      });
    }

    // Accessibility service — omitted entirely from the Play build. The Java
    // class still compiles into the APK but without a manifest declaration it
    // can never be bound or enabled.
    if (!PLAY_BUILD && !existingServices.includes(".VerifAIAccessibilityService")) {
      app.service.push({
        $: {
          "android:name": ".VerifAIAccessibilityService",
          "android:exported": "true",
          "android:label": "VerifAI Auto-Detect",
          "android:permission": "android.permission.BIND_ACCESSIBILITY_SERVICE",
        },
        "intent-filter": [{
          action: [{ $: { "android:name": "android.accessibilityservice.AccessibilityService" } }],
        }],
        "meta-data": [{
          $: {
            "android:name": "android.accessibilityservice",
            "android:resource": "@xml/accessibility_service_config",
          }
        }]
      });
    }

    // Invisible clipboard-reader activity (Android 10+ clipboard focus workaround)
    if (!app.activity) app.activity = [];
    const existingActivities = app.activity.map((a) => a.$["android:name"]);
    if (!existingActivities.includes(".ClipboardReaderActivity")) {
      app.activity.push({
        $: {
          "android:name": ".ClipboardReaderActivity",
          "android:exported": "false",
          "android:theme": "@android:style/Theme.Translucent.NoTitleBar",
          "android:excludeFromRecents": "true",
          "android:noHistory": "true",
          "android:taskAffinity": "",
        },
      });
    }

    // Transparent activity that requests screen-capture consent
    if (!existingActivities.includes(".MediaProjectionRequestActivity")) {
      app.activity.push({
        $: {
          "android:name": ".MediaProjectionRequestActivity",
          "android:exported": "false",
          "android:theme": "@android:style/Theme.Translucent.NoTitleBar",
          "android:excludeFromRecents": "true",
          "android:noHistory": "true",
          "android:taskAffinity": "",
        },
      });
    }

    // Add share intent filters to main activity
    const activity = app.activity?.[0];
    if (activity) {
      if (!activity["intent-filter"]) activity["intent-filter"] = [];
      const filters = activity["intent-filter"];
      const hasVideoFilter = filters.some((f) =>
        f.data?.some((d) => d.$["android:mimeType"] === "video/*")
      );
      if (!hasVideoFilter) {
        filters.push({
          action: [{ $: { "android:name": "android.intent.action.SEND" } }],
          category: [{ $: { "android:name": "android.intent.category.DEFAULT" } }],
          data: [{ $: { "android:mimeType": "video/*" } }],
        });
      }
    }

    return cfg;
  });
}

function withOverlayJavaFiles(config) {
  return withDangerousMod(config, [
    "android",
    (cfg) => {
      const projectRoot = cfg.modRequest.platformProjectRoot;
      // Must match the `package com.verifai.app;` declaration in the Java files
      // and the android.package in app.json
      const pkg = "com/verifai/app";
      const javaDestDir = path.join(
        projectRoot,
        "app/src/main/java",
        pkg
      );

      fs.mkdirSync(javaDestDir, { recursive: true });

      // Generated build flag consumed by the Java sources (OverlayService
      // branches on it). Regenerated on every prebuild.
      fs.writeFileSync(
        path.join(javaDestDir, "BuildFlags.java"),
        `package com.verifai.app;

/** Generated at prebuild by withAndroidOverlay.js — do not edit. */
public final class BuildFlags {
    /** Google Play variant: no accessibility service; the floating button
     *  analyzes via screen capture only. */
    public static final boolean PLAY_BUILD = ${PLAY_BUILD};
    private BuildFlags() {}
}
`
      );

      // Create accessibility service XML config (referenced from the manifest,
      // which the Play build doesn't declare)
      if (!PLAY_BUILD) {
      const xmlDir = path.join(projectRoot, "app/src/main/res/xml");
      fs.mkdirSync(xmlDir, { recursive: true });
      fs.writeFileSync(
        path.join(xmlDir, "accessibility_service_config.xml"),
        `<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeViewScrolled|typeWindowStateChanged|typeWindowContentChanged|typeViewClicked"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows"
    android:canRetrieveWindowContent="true"
    android:description="@string/app_name"
    android:notificationTimeout="100" />`
      );
      }

      // Copy the Java files
      for (const fname of [
        "OverlayService.java",
        "OverlayModule.java",
        "OverlayPackage.java",
        "VerifAIAccessibilityService.java",
        "GalleryWatcher.java",
        "ClipboardReaderActivity.java",
        "ScreenCaptureService.java",
        "MediaProjectionRequestActivity.java",
        "CrashLog.java",
      ]) {
        const src = path.join(JAVA_DIR, fname);
        const dst = path.join(javaDestDir, fname);
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, dst);
          console.log(`[withAndroidOverlay] Copied ${fname}`);
        } else {
          console.warn(`[withAndroidOverlay] WARNING: ${src} not found — skipping`);
        }
      }

      // Patch MainApplication.kt to register OverlayPackage
      const mainAppKt = path.join(
        projectRoot,
        "app/src/main/java",
        pkg,
        "MainApplication.kt"
      );
      if (fs.existsSync(mainAppKt)) {
        let src = fs.readFileSync(mainAppKt, "utf8");
        let changed = false;
        if (!src.includes("OverlayPackage")) {
          // Insert after "PackageList(this).packages" line
          src = src.replace(
            /val packages = PackageList\(this\)\.packages([^\n]*\n)/,
            (match) =>
              match +
              "          packages.add(com.verifai.app.OverlayPackage())\n"
          );
          changed = true;
        }
        // Global uncaught-exception recorder: any native crash (e.g. while
        // handling a shared video) is written to verifai_crash.txt, which the
        // JS shows on the next launch — so we get the exact stack trace instead
        // of only Android's opaque "can't open app" message. Re-raises after
        // logging so behaviour is otherwise unchanged.
        if (!src.includes("VerifAIUncaughtHandler")) {
          src = src.replace(
            /(super\.onCreate\(\)\n)/,
            (m) =>
              m +
              "    // VerifAIUncaughtHandler\n" +
              "    Thread.getDefaultUncaughtExceptionHandler().let { __prev ->\n" +
              "      Thread.setDefaultUncaughtExceptionHandler { __t, __e ->\n" +
              "        try { com.verifai.app.CrashLog.log(applicationContext, \"uncaught:\" + __t.name, __e) } catch (__ignored: Throwable) {}\n" +
              "        __prev?.uncaughtException(__t, __e)\n" +
              "      }\n" +
              "    }\n"
          );
          changed = true;
        }
        if (changed) {
          fs.writeFileSync(mainAppKt, src);
          console.log("[withAndroidOverlay] Patched MainApplication.kt");
        }
      } else {
        // Try MainApplication.java
        const mainAppJava = path.join(
          projectRoot,
          "app/src/main/java",
          pkg,
          "MainApplication.java"
        );
        if (fs.existsSync(mainAppJava)) {
          let src = fs.readFileSync(mainAppJava, "utf8");
          if (!src.includes("OverlayPackage")) {
            src = src.replace(
              /List<ReactPackage> packages = new PackageList\(this\)\.getPackages\(\);/,
              (match) =>
                match +
                "\n          packages.add(new com.verifai.app.OverlayPackage());"
            );
            fs.writeFileSync(mainAppJava, src);
            console.log("[withAndroidOverlay] Patched MainApplication.java");
          }
        }
      }

      return cfg;
    },
  ]);
}

// expo-share-intent@4.1.2's Android getFileInfo() uses hard `!!` assertions on
// contentResolver.query()/getType() and drives MediaMetadataRetriever from a
// content:// path — any of which throws (NPE / IllegalArgument / Security) for
// a good number of shared videos, and the throw propagates up through the
// share pipeline and crashes the app as it opens ("can't open app"). We wrap
// the getFileInfo call sites so a failure degrades to the minimal file info JS
// needs to upload the video, instead of taking down the process. Patches the
// library source in node_modules before Gradle compiles it.
function withShareIntentCrashFix(config) {
  return withDangerousMod(config, [
    "android",
    (cfg) => {
      const file = path.join(
        cfg.modRequest.projectRoot,
        "node_modules/expo-share-intent/android/src/main/java/expo/modules/shareintent/ExpoShareIntentModule.kt"
      );
      try {
        if (!fs.existsSync(file)) {
          console.warn("[shareIntentCrashFix] module .kt not found — skipping");
          return cfg;
        }
        let src = fs.readFileSync(file, "utf8");
        if (src.includes("shareIntentCrashFix")) return cfg; // idempotent

        // Minimal, always-safe file info: contentUri + a best-effort path, so
        // the JS side can still POST the file to /detect.
        const fallback =
          'mapOf("contentUri" to it.toString(), "filePath" to (instance?.getAbsolutePath(it) ?: it.toString()), "fileName" to (it.lastPathSegment ?: "shared"), "mimeType" to (instance?.currentActivity?.contentResolver?.getType(it) ?: instance?.context?.contentResolver?.getType(it) ?: "video/mp4"))';

        // A crash-proof wrapper around the library's getFileInfo. /* shareIntentCrashFix */
        const helper =
          "\n        private fun getFileInfoSafe(it: Uri): Map<String, String?> {\n" +
          "            return try { getFileInfo(it) } catch (e: Throwable) {\n" +
          "                android.util.Log.e(\"VerifAI\", \"getFileInfo failed, using fallback\", e)\n" +
          "                " + fallback + "\n" +
          "            }\n" +
          "        } /* shareIntentCrashFix */\n";

        // Route both call sites through the safe wrapper.
        src = src.replace(
          'notifyShareIntent(mapOf( "files" to arrayOf(getFileInfo(uri), "type" to "file")))',
          'notifyShareIntent(mapOf( "files" to arrayOf(getFileInfoSafe(uri), "type" to "file")))'
        );
        src = src.replace(
          "notifyShareIntent(mapOf( \"files\" to uris.map { getFileInfo(it) }, \"type\" to \"file\"))",
          "notifyShareIntent(mapOf( \"files\" to uris.map { getFileInfoSafe(it) }, \"type\" to \"file\"))"
        );

        // Inject the helper just before the existing getFileInfo definition.
        src = src.replace(
          "        private fun getFileInfo(uri: Uri): Map<String, String?> {",
          helper + "        private fun getFileInfo(uri: Uri): Map<String, String?> {"
        );

        fs.writeFileSync(file, src);
        console.log("[shareIntentCrashFix] Patched ExpoShareIntentModule.kt");
      } catch (e) {
        console.warn("[shareIntentCrashFix] skipped:", e.message);
      }
      return cfg;
    },
  ]);
}

module.exports = function withAndroidOverlay(config) {
  return withPlugins(config, [
    withOverlayManifest,
    withOverlayJavaFiles,
    withShareIntentCrashFix,
  ]);
};
