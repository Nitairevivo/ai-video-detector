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

    // Accessibility service
    if (!existingServices.includes(".VerifAIAccessibilityService")) {
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
      const pkg = "com/verifai/app";
      const javaDestDir = path.join(
        projectRoot,
        "app/src/main/java",
        pkg
      );

      fs.mkdirSync(javaDestDir, { recursive: true });

      // Create accessibility service XML config
      const xmlDir = path.join(projectRoot, "app/src/main/res/xml");
      fs.mkdirSync(xmlDir, { recursive: true });
      fs.writeFileSync(
        path.join(xmlDir, "accessibility_service_config.xml"),
        `<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeViewScrolled|typeWindowStateChanged|typeWindowContentChanged"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows"
    android:canRetrieveWindowContent="true"
    android:description="@string/app_name"
    android:notificationTimeout="100" />`
      );

      // Copy the Java files
      for (const fname of ["OverlayService.java", "OverlayModule.java", "OverlayPackage.java", "VerifAIAccessibilityService.java", "GalleryWatcher.java", "CrashLogger.java", "DiagModule.java", "DiagPackage.java"]) {
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
        if (!src.includes("OverlayPackage")) {
          let patched = false;
          // Pattern 1: val packages = PackageList(this).packages
          if (/val packages = PackageList\(this\)\.packages/.test(src)) {
            src = src.replace(
              /val packages = PackageList\(this\)\.packages([^\n]*\n)/,
              (match) =>
                match +
                "          packages.add(com.verifai.app.DiagPackage())\n" +
                "          packages.add(com.verifai.app.OverlayPackage())\n"
            );
            patched = true;
          // Pattern 2: PackageList(this).packages.apply { ... }
          } else if (/PackageList\(this\)\.packages\.apply\s*\{/.test(src)) {
            src = src.replace(
              /PackageList\(this\)\.packages\.apply\s*\{/,
              "PackageList(this).packages.apply {\n            add(com.verifai.app.DiagPackage())\n            add(com.verifai.app.OverlayPackage())"
            );
            patched = true;
          // Pattern 3: return packages (any return statement with a packages variable)
          } else if (/return\s+packages\b/.test(src)) {
            src = src.replace(
              /return\s+packages\b/,
              "packages.add(com.verifai.app.DiagPackage())\n          packages.add(com.verifai.app.OverlayPackage())\n          return packages"
            );
            patched = true;
          }
          if (patched) {
            console.log("[withAndroidOverlay] Patched getPackages in MainApplication.kt (DiagPackage + OverlayPackage)");
          } else {
            console.error("[withAndroidOverlay] ERROR: Could not find a pattern to patch getPackages!");
            console.error("[withAndroidOverlay] File preview:", src.slice(0, 800));
          }

          // Also inject early CrashLogger init into Application.onCreate (before super.onCreate)
          // so crashes during native-module initialization are captured
          if (!src.includes("CrashLogger.init") && /override fun onCreate\(\)/.test(src)) {
            src = src.replace(
              /override fun onCreate\(\)\s*\{/,
              "override fun onCreate() {\n        com.verifai.app.CrashLogger.init(this)"
            );
            console.log("[withAndroidOverlay] Injected early CrashLogger.init into Application.onCreate");
          }

          fs.writeFileSync(mainAppKt, src);
        } else {
          console.log("[withAndroidOverlay] MainApplication.kt already contains OverlayPackage");
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
                "\n          packages.add(new com.aivideodector.app.OverlayPackage());"
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

module.exports = function withAndroidOverlay(config) {
  return withPlugins(config, [withOverlayManifest, withOverlayJavaFiles]);
};
