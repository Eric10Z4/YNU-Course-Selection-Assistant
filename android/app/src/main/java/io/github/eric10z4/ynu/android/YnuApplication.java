package io.github.eric10z4.ynu.android;

import android.app.Application;
import android.net.*;
import org.json.JSONObject;

public final class YnuApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        RuntimeHost host = RuntimeHost.get(this);
        ConnectivityManager manager = getSystemService(ConnectivityManager.class);
        Network initial=manager.getActiveNetwork();
        publish(host,initial,initial==null?null:manager.getNetworkCapabilities(initial));
        manager.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
            private Network current=initial;
            @Override public void onAvailable(Network network) { current=network; publish(host,network,null); }
            @Override public void onLost(Network network) {
                if (network.equals(current)) { current=null; publish(host,null,null); }
            }
            @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
                if (network.equals(current)) publish(host,network,caps);
            }
        });
    }
    private void publish(RuntimeHost host,Network network,NetworkCapabilities caps) {
        try {
            JSONObject status=new JSONObject();
            status.put("available",caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
            status.put("validated",caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED));
            status.put("captive",caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL));
            status.put("identity",network==null?"":network.toString());
            host.network(status.toString());
        } catch (Exception ignored) { }
    }
}
