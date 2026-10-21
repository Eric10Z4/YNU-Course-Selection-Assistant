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
import org.json.JSONArray;
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
        // Gradle may uninstall the tested app before adb can collect its data.
        // Keep only these synthetic reports in the test emulator's shell area.
        shell("mkdir -p /data/local/tmp/ynu-device-reports");
        shell("cp "+new File(directory,name).getAbsolutePath()+" /data/local/tmp/ynu-device-reports/"+name);
        assertEquals("Synthetic report retained outside test-app cleanup",text,shellOutput("cat /data/local/tmp/ynu-device-reports/"+name));
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
    private void shell(String command) throws Exception {
        shellOutput(command);
    }
    private String shellOutput(String command) throws Exception {
        try (InputStream stream=new ParcelFileDescriptor.AutoCloseInputStream(getInstrumentation().getUiAutomation().executeShellCommand(command))) {
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            byte[] buffer=new byte[1024]; int count;
            while ((count=stream.read(buffer))!=-1) output.write(buffer,0,count);
            return output.toString("UTF-8");
        }
    }
    private void waitNetwork(boolean available) throws Exception {
        long until=SystemClock.elapsedRealtime()+25000;
        while (SystemClock.elapsedRealtime()<until) {
            JSONObject current=host.snapshot();
            if (current!=null && current.getJSONObject("network").getBoolean("available")==available) return;
            Thread.sleep(200);
        }
        fail("Native connectivity callback did not reach available="+available);
    }
    private void wifi(boolean enabled) throws Exception {
        if (Build.VERSION.SDK_INT<29) {
            android.net.wifi.WifiManager manager=(android.net.wifi.WifiManager)context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            assertTrue("Legacy test Wi-Fi control accepted",manager.setWifiEnabled(enabled));
        } else shell("svc wifi "+(enabled?"enable":"disable"));
    }
    @Test(timeout=120000) public void testNativeConnectivityDisconnectAndRestore() throws Exception {
        org.junit.Assume.assumeTrue("Only toggle test-emulator radios",Build.HARDWARE.equals("ranchu") || Build.HARDWARE.equals("goldfish"));
        try {
            wifi(false); shell("svc data disable"); waitNetwork(false);
            wifi(true); shell("svc data enable"); waitNetwork(true);
            wifi(false); shell("svc data disable"); waitNetwork(false);
        } finally {
            wifi(true); shell("svc data enable");
        }
        waitNetwork(true);
        report("connectivity.json",new JSONObject().put("native_disconnect",true).put("native_restore",true).toString());
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
            getInstrumentation().runOnMainSync(()->{
                activity.webViewForTesting().getSettings().setTextZoom(160);
                activity.webViewForTesting().requestFocus();
            });
            js(activity,"tab('account'); document.getElementById('password').scrollIntoView();");
            Thread.sleep(300);
            JSONArray point=new JSONArray(js(activity,"(function(){var r=document.getElementById('password').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2,window.devicePixelRatio];})()"));
            int[] origin=new int[2];
            getInstrumentation().runOnMainSync(()->activity.webViewForTesting().getLocationOnScreen(origin));
            float x=(float)(origin[0]+activity.webViewForTesting().getPaddingLeft()+point.getDouble(0)*point.getDouble(2));
            float y=(float)(origin[1]+activity.webViewForTesting().getPaddingTop()+point.getDouble(1)*point.getDouble(2));
            long down=SystemClock.uptimeMillis();
            getInstrumentation().sendPointerSync(android.view.MotionEvent.obtain(down,down,android.view.MotionEvent.ACTION_DOWN,x,y,0));
            getInstrumentation().sendPointerSync(android.view.MotionEvent.obtain(down,down+80,android.view.MotionEvent.ACTION_UP,x,y,0));
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
