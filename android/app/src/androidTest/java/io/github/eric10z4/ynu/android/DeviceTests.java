package io.github.eric10z4.ynu.android;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.os.*;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.*;
import com.chaquo.python.Python;
import org.json.JSONObject;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

@SuppressWarnings("deprecation")
public final class DeviceTests {
    private Context context;
    private RuntimeHost host;
    private Instrumentation getInstrumentation() { return InstrumentationRegistry.getInstrumentation(); }
    @Before public void setUp() throws Exception {
        context=getInstrumentation().getTargetContext(); host=RuntimeHost.get(context);
        long until=SystemClock.elapsedRealtime()+60000;
        while (!host.ready() && SystemClock.elapsedRealtime()<until) Thread.sleep(100);
        assertTrue("Python/requests/shared engine initialization",host.ready());
    }
    private void report(String name,String text) throws Exception {
        File directory=context.getExternalFilesDir(null); assertNotNull(directory);
        try (FileOutputStream out=new FileOutputStream(new File(directory,name))) { out.write(text.getBytes("UTF-8")); }
    }
    private MainActivity activity() {
        Intent intent=new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return (MainActivity)getInstrumentation().startActivitySync(intent);
    }
    private String js(MainActivity activity,String script) throws Exception {
        CountDownLatch ready=new CountDownLatch(1); AtomicReference<String> value=new AtomicReference<>();
        getInstrumentation().runOnMainSync(()->activity.webViewForTesting().evaluateJavascript(script,result->{value.set(result);ready.countDown();}));
        assertTrue("WebView response",ready.await(15,TimeUnit.SECONDS)); return value.get();
    }
    private void waitPage(MainActivity activity) throws Exception {
        long until=SystemClock.elapsedRealtime()+20000;
        while (SystemClock.elapsedRealtime()<until) {
            if ("true".equals(js(activity,"document.readyState==='complete' && typeof refresh==='function'"))) return;
            Thread.sleep(200);
        }
        fail("Mobile page/JavaScript did not initialize");
    }
    @Test public void testRecoveryScenariosInsideAndroidPython() throws Exception {
        String result=Python.getInstance().getModule("test_android").callAttr("run_device_tests").toString();
        report("recovery.json",result); assertTrue(result,new JSONObject(result).getBoolean("passed"));
    }
    @Test public void testNativeOcrAndTransparentImage() throws Exception {
        Bitmap blank=Bitmap.createBitmap(120,40,Bitmap.Config.ARGB_8888); blank.eraseColor(Color.WHITE);
        ByteArrayOutputStream bytes=new ByteArrayOutputStream(); blank.compress(Bitmap.CompressFormat.PNG,100,bytes);
        String white=host.ocr.classify(bytes.toByteArray());
        blank.eraseColor(Color.TRANSPARENT); bytes.reset(); blank.compress(Bitmap.CompressFormat.PNG,100,bytes);
        String transparent=host.ocr.classify(bytes.toByteArray()); blank.recycle();
        assertEquals("Transparent pixels composite over white",white,transparent);
        report("ocr.json",new JSONObject().put("passed",true).put("scope","synthetic blank/transparent inference; no recognition-rate claim").toString());
    }
    @Test public void testPasswordIsOptInAndEncrypted() throws Exception {
        host.vault.save("{\"password\":\"synthetic-test-password\",\"remember\":false}");
        assertFalse(new JSONObject(host.vault.load()).has("password"));
        host.vault.save("{\"password\":\"synthetic-test-password\",\"remember\":true}");
        assertEquals("synthetic-test-password",new JSONObject(host.vault.load()).getString("password"));
        String stored=context.getSharedPreferences("private_config",Context.MODE_PRIVATE).getString("encrypted","");
        assertFalse(stored.contains("synthetic-test-password")); host.vault.save("{}");
    }
    @Test public void testWebViewBridgeAndSmallScreen() throws Exception {
        MainActivity activity=activity();
        try {
            waitPage(activity);
            assertEquals("No horizontal overflow","true",js(activity,"document.documentElement.scrollWidth<=window.innerWidth+1"));
            js(activity,"window.__bridge=null; native('snapshot').then(function(r){window.__bridge=r.ok;});");
            long until=SystemClock.elapsedRealtime()+15000;
            while (!"true".equals(js(activity,"window.__bridge")) && SystemClock.elapsedRealtime()<until) Thread.sleep(100);
            assertEquals("Native bridge to actual Python runtime","true",js(activity,"window.__bridge"));
            js(activity,"tab('account')");
            assertEquals("Account page reachable","false",js(activity,"document.getElementById('page-account').hidden"));
            Bitmap screenshot=getInstrumentation().getUiAutomation().takeScreenshot();
            try (FileOutputStream out=new FileOutputStream(new File(context.getExternalFilesDir(null),"mobile-account.png"))) { screenshot.compress(Bitmap.CompressFormat.PNG,100,out); }
            screenshot.recycle();
            report("ui.json",new JSONObject().put("api",Build.VERSION.SDK_INT).put("bridge",true).put("no_horizontal_overflow",true).toString());
        } finally { getInstrumentation().runOnMainSync(activity::finish); }
    }
    private MainActivity startSyntheticService() throws Exception {
        long closed=SystemClock.elapsedRealtime()+5000;
        while (TaskService.instance!=null && SystemClock.elapsedRealtime()<closed) Thread.sleep(50);
        host.control.submit(()->{}).get(5,TimeUnit.SECONDS);
        if (Build.VERSION.SDK_INT>=33) {
            ParcelFileDescriptor command=getInstrumentation().getUiAutomation().executeShellCommand("pm grant "+context.getPackageName()+" android.permission.POST_NOTIFICATIONS");
            command.close();
        }
        MainActivity activity=activity(); waitPage(activity);
        String payload=Python.getInstance().getModule("test_android").callAttr("install_offline_scenario").toString();
        assertTrue(new JSONObject(host.call("start",payload)).getBoolean("ok"));
        getInstrumentation().runOnMainSync(()->activity.startForegroundService(new Intent(context,TaskService.class)));
        long until=SystemClock.elapsedRealtime()+10000;
        while (TaskService.instance==null && SystemClock.elapsedRealtime()<until) Thread.sleep(50);
        assertNotNull("Foreground service started",TaskService.instance);
        return activity;
    }
    @Test public void testLargeTextAndKeyboardLayout() throws Exception {
        MainActivity activity=activity();
        try {
            waitPage(activity);
            getInstrumentation().runOnMainSync(()->activity.webViewForTesting().getSettings().setTextZoom(160));
            js(activity,"tab('account'); document.getElementById('password').focus(); document.getElementById('password').scrollIntoView();");
            getInstrumentation().runOnMainSync(()->{
                activity.webViewForTesting().requestFocus();
                activity.getSystemService(android.view.inputmethod.InputMethodManager.class).showSoftInput(activity.webViewForTesting(),0);
            });
            Thread.sleep(1000);
            assertEquals("Large text has no horizontal overflow","true",js(activity,"document.documentElement.scrollWidth<=window.innerWidth+1"));
            assertEquals("Password field remains editable","true",js(activity,"document.activeElement.id==='password'"));
            report("large-text.json",new JSONObject().put("text_zoom",160).put("no_horizontal_overflow",true).put("editable_field",true).toString());
        } finally { getInstrumentation().runOnMainSync(activity::finish); }
    }
    @Test public void testNotificationStopWithoutSchoolTraffic() throws Exception {
        MainActivity activity=startSyntheticService();
        try {
            assertTrue(host.snapshot().getBoolean("active"));
            getInstrumentation().runOnMainSync(()->context.startService(new Intent(context,TaskService.class).setAction(TaskService.STOP)));
            long until=SystemClock.elapsedRealtime()+5000;
            while (host.snapshot().optBoolean("active") && SystemClock.elapsedRealtime()<until) Thread.sleep(50);
            assertFalse(host.snapshot().getBoolean("active"));
            assertEquals("stopped",host.snapshot().getString("state"));
        } finally { getInstrumentation().runOnMainSync(activity::finish); }
    }
    @Test public void testSystemTimeoutCallbackStopsService() throws Exception {
        if (Build.VERSION.SDK_INT<35) return;
        MainActivity activity=startSyntheticService();
        try {
            getInstrumentation().runOnMainSync(()->TaskService.instance.onTimeout(1,1));
            long until=SystemClock.elapsedRealtime()+5000;
            while (host.snapshot().optBoolean("active") && SystemClock.elapsedRealtime()<until) Thread.sleep(50);
            assertFalse(host.snapshot().getBoolean("active"));
            assertTrue(host.snapshot().getString("message").contains("系统后台运行时限"));
        } finally { getInstrumentation().runOnMainSync(activity::finish); }
    }
}
