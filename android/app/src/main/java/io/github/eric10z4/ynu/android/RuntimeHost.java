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
    volatile long serviceGeneration;
    private long pendingStart;
    private long nextStart;
    private long startRevision;
    private long cancellationGeneration;
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
                module = initialized;
                control.execute(() -> initialized.callAttr("network", network));
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
    public synchronized long reserveStart() {
        pendingStart = ++nextStart;
        startRevision++;
        return pendingStart;
    }
    public synchronized void cancelStart(long token) {
        if (pendingStart == token) cancelPendingStart();
    }
    public synchronized void cancelPendingStart() { pendingStart = 0; startRevision++; }
    public synchronized boolean hasPendingStart() { return pendingStart != 0; }
    public synchronized boolean isPendingStart(long token) { return pendingStart == token; }
    public synchronized long operationGeneration() { return cancellationGeneration; }
    public synchronized void cancelOperations() { cancellationGeneration++; cancelPendingStart(); }
    public synchronized long newServiceGeneration() { return ++serviceGeneration; }
    public synchronized long startRevision() { return startRevision; }
    public synchronized boolean canRetire(long revision) { return pendingStart == 0 && startRevision == revision; }
    public String start(long token, String method, String payload) throws Exception {
        // Slow queries stay on actions. Validate and start on control so a later
        // stop cannot be overtaken by a queued start which clears Python's stop flag.
        return control.submit(() -> {
            synchronized (this) {
                if (pendingStart != token) return "{\"ok\":false,\"msg\":\"启动已取消，请手动重新开始\"}";
                try { return call(method, payload); }
                finally { cancelStart(token); }
            }
        }).get();
    }
    public String withdraw(long generation, String payload) throws Exception {
        boolean prepared = control.submit(() -> {
            synchronized (this) {
                return cancellationGeneration == generation && module != null && module.callAttr("prepare_withdraw").toBoolean();
            }
        }).get();
        if (!prepared) return "{\"ok\":false,\"msg\":\"退选已取消，请手动重新操作\"}";
        return call("withdraw", payload);
    }
    public void stop(String message) {
        cancelOperations();
        control.execute(() -> { if (module != null) module.callAttr("stop", message); });
    }
    public void serviceEnded(String message, long generation, boolean onlyIfActive) {
        control.execute(() -> {
            synchronized (this) {
                if (serviceGeneration != generation) return;
                boolean pending = hasPendingStart();
                cancelOperations();
                if (module == null) return;
                JSONObject current = snapshot();
                if (!onlyIfActive || pending || (current != null && current.optBoolean("active"))) module.callAttr("stop", message);
            }
        });
    }
}
