const {
  withAndroidManifest,
  withDangerousMod,
  withPlugins,
} = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

const PLUGIN_DIR = __dirname;

// Nuclear Build 10: ONLY DiagModule — no OverlayModule, no services, no CrashLogger.
// Goal: confirm the app can open at all before re-adding complex native code.

function withOverlayManifest(config) {
  return withAndroidManifest(config, (cfg) => {
    const manifest = cfg.modResults.manifest;
    if (!manifest["uses-permission"]) manifest["uses-permission"] = [];
    const existingPerms = manifest["uses-permission"].map((p) => p.$["android:name"]);
    if (!existingPerms.includes("android.permission.SYSTEM_ALERT_WINDOW")) {
      manifest["uses-permission"].push({ $: { "android:name": "android.permission.SYSTEM_ALERT_WINDOW" } });
    }
    return cfg;
  });
}

function withDiagJavaFiles(config) {
  return withDangerousMod(config, [
    "android",
    (cfg) => {
      const projectRoot = cfg.modRequest.platformProjectRoot;
      const pkg = "com/verifai/app";
      const javaDestDir = path.join(projectRoot, "app/src/main/java", pkg);
      fs.mkdirSync(javaDestDir, { recursive: true });

      // Copy ONLY DiagModule and DiagPackage — nothing else
      for (const fname of ["DiagModule.java", "DiagPackage.java"]) {
        const src = path.join(PLUGIN_DIR, fname);
        const dst = path.join(javaDestDir, fname);
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, dst);
          console.log(`[withAndroidOverlay] Copied ${fname}`);
        } else {
          console.warn(`[withAndroidOverlay] WARNING: ${src} not found — skipping`);
        }
      }

      // Patch MainApplication.kt to register DiagPackage ONLY
      const mainAppKt = path.join(projectRoot, "app/src/main/java", pkg, "MainApplication.kt");
      if (fs.existsSync(mainAppKt)) {
        let src = fs.readFileSync(mainAppKt, "utf8");
        if (!src.includes("DiagPackage")) {
          let patched = false;
          if (/val packages = PackageList\(this\)\.packages/.test(src)) {
            src = src.replace(
              /val packages = PackageList\(this\)\.packages([^\n]*\n)/,
              (match) => match + "          packages.add(com.verifai.app.DiagPackage())\n"
            );
            patched = true;
          } else if (/PackageList\(this\)\.packages\.apply\s*\{/.test(src)) {
            src = src.replace(
              /PackageList\(this\)\.packages\.apply\s*\{/,
              "PackageList(this).packages.apply {\n            add(com.verifai.app.DiagPackage())"
            );
            patched = true;
          } else if (/return\s+packages\b/.test(src)) {
            src = src.replace(
              /return\s+packages\b/,
              "packages.add(com.verifai.app.DiagPackage())\n          return packages"
            );
            patched = true;
          }
          if (patched) {
            fs.writeFileSync(mainAppKt, src);
            console.log("[withAndroidOverlay] Patched MainApplication.kt (DiagPackage only)");
          } else {
            // Log the full content so we can see what pattern the generated code uses
            console.error("[withAndroidOverlay] ERROR: No pattern matched getPackages — DiagPackage NOT registered");
            console.error("[withAndroidOverlay] MainApplication.kt content:\n" + src.slice(0, 1500));
          }
        } else {
          console.log("[withAndroidOverlay] MainApplication.kt already has DiagPackage");
        }
      } else {
        console.warn("[withAndroidOverlay] MainApplication.kt not found");
      }

      return cfg;
    },
  ]);
}

module.exports = function withAndroidOverlay(config) {
  return withPlugins(config, [withOverlayManifest, withDiagJavaFiles]);
};
