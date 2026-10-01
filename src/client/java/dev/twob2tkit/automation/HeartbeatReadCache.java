package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.util.Objects;

/** Cache file observation only; heartbeat timestamp validity and safety TTL remain live checks. */
final class HeartbeatReadCache {
    static final long INTERVAL_MILLIS=100;
    interface Reader { JsonObject read() throws Exception; }
    private String lease,leaseWorld,clientWorld;
    private long readAt;
    private boolean observed;
    private JsonObject cached;
    JsonObject read(String lease,String leaseWorld,String clientWorld,long now,Reader reader)throws Exception {
        if(!observed||!Objects.equals(this.lease,lease)||!Objects.equals(this.leaseWorld,leaseWorld)
                ||!Objects.equals(this.clientWorld,clientWorld)||now<readAt||now-readAt>=INTERVAL_MILLIS){
            // Clear before IO so a failed new scope cannot inherit an older controller's file.
            this.lease=lease;this.leaseWorld=leaseWorld;this.clientWorld=clientWorld;readAt=now;
            cached=null;observed=false;
            cached=reader.read();observed=true;
        }
        return cached;
    }
}
