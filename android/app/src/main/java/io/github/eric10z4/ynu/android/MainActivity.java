package io.github.eric10z4.ynu.android;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.*;
import android.webkit.*;
import android.view.*;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class MainActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private WebView web;
    private volatile boolean visible;
    private RuntimeHost host;
    public WebView webViewForTesting() { return web; }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state); host = RuntimeHost.get(this);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        web = new WebView(this); web.setBackgroundColor(Color.rgb(245,247,251));
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setAllowFileAccess(false); web.getSettings().setAllowContentAccess(false);
        web.getSettings().setJavaScriptCanOpenWindowsAutomatically(false);
        web.getSettings().setSafeBrowsingEnabled(true);
        web.getSettings().setTextZoom(Math.round(getResources().getConfiguration().fontScale * 100));
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return true; }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String path = request.getUrl().getPath();
                if (ORIGIN.equals(request.getUrl().getScheme() + "://" + request.getUrl().getHost()) &&
                        Arrays.asList("/index.html", "/app.js", "/style.css").contains(path)) {
                    try {
                        String mime = path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html";
                        return new WebResourceResponse(mime, "utf-8", getAssets().open("mobile" + path));
                    } catch (IOException ignored) { }
                }
                return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
            }
        });
        web.addJavascriptInterface(new Bridge(), "YnuNative");
        setContentView(web);
        web.setOnApplyWindowInsetsListener((view, insets) -> {
            int left, top, right, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets system = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                left=system.left; top=system.top; right=system.right; bottom=system.bottom;
            } else { left=insets.getSystemWindowInsetLeft(); top=insets.getSystemWindowInsetTop(); right=insets.getSystemWindowInsetRight(); bottom=insets.getSystemWindowInsetBottom(); }
            view.setPadding(left,top,right,bottom); return insets;
        });
        web.loadUrl(ORIGIN + "/index.html");
    }
    private void result(String id, String value) {
        runOnUiThread(() -> { if (!isDestroyed()) web.evaluateJavascript("window.nativeResult(" + JSONObject.quote(id) + "," + value + ")", null); });
    }
    public final class Bridge {
        @JavascriptInterface public void request(String id, String method, String payload) {
            if (id.length() > 80 || payload.length() > 200000) return;
            if (!Arrays.asList("snapshot","load_config","save_config","batches","types","query","selected","timetable","start","resume","stop","withdraw","recheck","confirm_review").contains(method)) return;
            Runnable action = () -> {
                try {
                    if (method.equals("load_config")) result(id, new JSONObject().put("ok",true).put("cfg",new JSONObject(host.vault.load())).toString());
                    else if (method.equals("save_config")) { host.vault.save(new JSONObject(payload).getJSONObject("cfg").toString()); result(id,"{\"ok\":true}"); }
                    else {
                        String response = host.call(method, payload);
                        result(id, response);
                        if ((method.equals("start") || method.equals("resume")) && !new JSONObject(response).optBoolean("ok")) {
                            JSONObject current = host.snapshot();
                            if (current == null || !current.optBoolean("active")) stopService(new Intent(MainActivity.this, TaskService.class));
                        }
                    }
                } catch (Exception e) { result(id, "{\"ok\":false,\"msg\":\"操作未完成，请核对任务状态\"}"); }
            };
            if (method.equals("start") || method.equals("resume")) {
                runOnUiThread(() -> {
                    if (!visible) { result(id,"{\"ok\":false,\"msg\":\"请回到应用前台启动任务\"}"); return; }
                    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
                        result(id,"{\"ok\":false,\"msg\":\"请允许任务通知后，再点击开始\"}"); return;
                    }
                    try { host.serviceGeneration++; startForegroundService(new Intent(MainActivity.this, TaskService.class)); host.actions.execute(action); }
                    catch (Exception e) { result(id,"{\"ok\":false,\"msg\":\"系统未允许后台服务，请保持前台后重试\"}"); }
                });
            } else if (method.equals("snapshot") || method.equals("stop")) host.control.execute(action);
            else host.actions.execute(action);
        }
    }
    @Override protected void onResume() { super.onResume(); visible=true; }
    @Override protected void onPause() { visible=false; super.onPause(); }
    @Override protected void onDestroy() { web.removeJavascriptInterface("YnuNative"); web.destroy(); super.onDestroy(); }
}
