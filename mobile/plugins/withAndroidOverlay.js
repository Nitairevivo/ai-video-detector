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
      "android.permission.RECEIVE_BOOT_COMPLETED",
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
      const pkg = "com/aivideodector/app";
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
    android:accessibilityEventTypes="typeViewScrolled|typeWindowStateChanged|typeWindowContentChanged|typeViewClicked"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows"
    android:canRetrieveWindowContent="true"
    android:description="@string/app_name"
    android:notificationTimeout="100" />`
      );

      // Copy the Java files
      for (const fname of ["OverlayService.java", "OverlayModule.java", "OverlayPackage.java", "VerifAIAccessibilityService.java"]) {
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
          src = src.replace(
            "override fun getPackages(): List<ReactPackage>",
            `override fun getPackages(): List<ReactPackage>`
          );
          // Insert after "PackageList(this).packages" line
          src = src.replace(
            /val packages = PackageList\(this\)\.packages([^\n]*\n)/,
            (match) =>
              match +
              "          packages.add(com.aivideodector.app.OverlayPackage())\n"
          );
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
