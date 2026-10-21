package io.github.eric10z4.ynu.android;

import android.content.Context;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.util.concurrent.*;

public final class RuntimeHost {
    private static RuntimeHost instance;
    public final ExecutorService actions = Executors.newSingleThreadExecutor();
    public final ExecutorService control = Executors.newSingleThreadExecutor();
    public final NativeOcr ocr;
    public final CredentialVault vault;
    private volatile PyObject module;
    private volatile String initializationError;
    private volatile String network = "{\"available\":false,\"captive\":false,\"validated\":false}";
    public static synchronized RuntimeHost get(Context context) {
        if (instance == null) instance = new RuntimeHost(context.getApplicationContext());
        return instance;
    }
    private RuntimeHost(Context context) {
        ocr = new NativeOcr(context); vault = new CredentialVault(context);
        actions.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
                PyObject initialized = Python.getInstance().getModule("android_runtime");
                initialized.callAttr("initialize", context.getFilesDir().getAbsolutePath(), ocr);
                initialized.callAttr("network", network); module = initialized;
            } catch (Exception e) {
                android.util.Log.e("YNU", "Engine initialization failed", e);
                initializationError = "移动端引擎初始化失败，请反馈应用版本和设备型号";
            }
        });
    }
    public boolean ready() { return module != null; }
    public String call(String method, String payload) {
        if (module == null) return "{\"ok\":false,\"msg\":\"" + (initializationError == null ? "引擎准备中，请稍候" : initializationError) + "\"}";
        return module.callAttr("call", method, payload).toString();
    }
    public JSONObject snapshot() {
        try { return new JSONObject(call("snapshot", "{}")).optJSONObject("snapshot"); }
        catch (Exception e) { return null; }
    }
    public void network(String value) {
        network = value;
        control.execute(() -> { if (module != null) module.callAttr("network", value); });
    }
    public void stop(String message) {
        control.execute(() -> { if (module != null) module.callAttr("stop", message); });
    }
}
