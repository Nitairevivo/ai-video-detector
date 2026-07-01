package com.verifai.app;

import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;

public class DiagModule extends ReactContextBaseJavaModule {
    public DiagModule(ReactApplicationContext ctx) {
        super(ctx);
    }

    @Override
    public String getName() { return "DiagModule"; }

    @ReactMethod
    public void getError(Promise promise) {
        try {
            android.content.Context ctx = getReactApplicationContext().getApplicationContext();
            String pkgErr = CrashLogger.packageInitError;
            String crash = CrashLogger.getAndClear(ctx);
            String result = "";
            if (pkgErr != null) result += "PKG_INIT_FAIL: " + pkgErr;
            if (crash != null) result += (result.isEmpty() ? "" : "\n") + "CRASH: " + crash;
            promise.resolve(result.isEmpty() ? null : result);
        } catch (Exception e) {
            promise.reject("DIAG_ERR", e.toString());
        }
    }
}
