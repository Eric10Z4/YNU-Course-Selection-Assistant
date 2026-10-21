package io.github.eric10z4.ynu.android;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import org.json.JSONObject;
import java.util.Arrays;

public final class TaskService extends Service {
    static volatile TaskService instance;
    public static final String STOP = "io.github.eric10z4.ynu.STOP";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private PowerManager.WakeLock wakeLock;
    private long started;
    private volatile boolean destroyed;
    private final Runnable heartbeat = new Runnable() {
        @Override public void run() {
            RuntimeHost host = RuntimeHost.get(TaskService.this);
            host.control.execute(() -> {
                JSONObject snapshot = host.snapshot();
                handler.post(() -> {
                    if (destroyed) return;
                    if (snapshot != null && !snapshot.optBoolean("active") && SystemClock.elapsedRealtime() - started > 15000) { stopSelf(); return; }
                    if (SystemClock.elapsedRealtime() - started > 3 * 60 * 60 * 1000L) { host.stop("后台服务运行时长已到，请手动恢复"); stopSelf(); return; }
                    getSystemService(NotificationManager.class).notify(7, notification(snapshot == null ? "引擎准备中" : snapshot.optString("message")));
                    String state = snapshot == null ? "" : snapshot.optString("state");
                    boolean executing = Arrays.asList("running", "submitting", "reconciling", "waiting_start").contains(state);
                    if (wakeLock != null && executing) wakeLock.acquire(120000L);
                    else if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
                    handler.postDelayed(heartbeat, 30000);
                });
            });
        }
    };
    private Notification notification(String text) {
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, TaskService.class).setAction(STOP), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, "tasks").setSmallIcon(android.R.drawable.ic_popup_sync).setContentTitle("YNU 任务状态")
            .setContentText(text).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(null, "停止任务", stop).build()).build();
    }
    @Override public void onCreate() {
        instance = this;
        super.onCreate(); started = SystemClock.elapsedRealtime();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("tasks", "选课任务", NotificationManager.IMPORTANCE_LOW));
        if (Build.VERSION.SDK_INT >= 29) startForeground(7, notification("正在准备任务"), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(7, notification("正在准备任务"));
        wakeLock = getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, getPackageName() + ":task");
        wakeLock.setReferenceCounted(false); wakeLock.acquire(120000L);
        handler.post(heartbeat);
    }
    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent != null && STOP.equals(intent.getAction())) { RuntimeHost.get(this).stop("用户从通知栏停止任务"); stopSelf(); }
        return START_NOT_STICKY;
    }
    @Override public void onTimeout(int startId, int type) {
        RuntimeHost.get(this).stop("系统后台运行时限已到，任务已暂停，请手动核对恢复");
        stopSelf();
    }
    @Override public void onDestroy() {
        instance = null;
        destroyed = true;
        handler.removeCallbacksAndMessages(null);
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        RuntimeHost host = RuntimeHost.get(this);
        host.control.execute(() -> {
            JSONObject snapshot = host.snapshot();
            if (snapshot != null && snapshot.optBoolean("active")) host.stop("后台服务已结束；请核对后手动恢复");
        });
        stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
