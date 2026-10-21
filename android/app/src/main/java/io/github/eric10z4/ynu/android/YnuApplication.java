package io.github.eric10z4.ynu.android;

import android.app.Application;
import android.net.*;
import org.json.JSONObject;

public final class YnuApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        RuntimeHost host = RuntimeHost.get(this);
        ConnectivityManager manager = getSystemService(ConnectivityManager.class);
        Runnable update = () -> {
            Network current = manager.getActiveNetwork();
            NetworkCapabilities caps = current == null ? null : manager.getNetworkCapabilities(current);
            try {
                JSONObject status = new JSONObject();
                status.put("available", caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
                status.put("validated", caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED));
                status.put("captive", caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL));
                status.put("identity", current == null ? "" : current.toString());
                host.network(status.toString());
            } catch (Exception ignored) { }
        };
        manager.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) { update.run(); }
            @Override public void onLost(Network network) { update.run(); }
            @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) { update.run(); }
        });
        update.run();
    }
}
