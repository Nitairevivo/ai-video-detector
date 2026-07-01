package com.verifai.app;

import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;

public class DiagModule extends ReactContextBaseJavaModule {
    public DiagModule(ReactApplicationContext ctx) { super(ctx); }

    @Override
    public String getName() { return "DiagModule"; }

    @ReactMethod
    public void getError(Promise promise) {
        promise.resolve("DiagModule_v10_OK");
    }
}
