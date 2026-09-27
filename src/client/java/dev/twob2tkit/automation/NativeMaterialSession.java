package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.world.phys.Vec3;

/** Client-tick owner for the existing material automation primitives. */
public final class NativeMaterialSession {
    final String job,lease,world;
    final Vec3 parkTarget;
    long revision,lastTouch;
    String pendingId;
    JsonObject queued;
    JsonObject immediate;
    boolean closed;

    NativeMaterialSession(String job,String lease,String world,long revision,Vec3 parkTarget){
        this.job=job;this.lease=lease;this.world=world;this.revision=revision;
        this.parkTarget=parkTarget;this.lastTouch=System.currentTimeMillis();
    }

    public static NativeMaterialSession open(Minecraft c,Vec3 parkTarget){
        return AutomationBridge.nativeMaterialOpen(c,parkTarget);
    }
    public String submit(Minecraft c,String op,JsonObject params){
        return AutomationBridge.nativeMaterialSubmit(this,c,op,params);
    }
    public JsonObject poll(Minecraft c){return AutomationBridge.nativeMaterialPoll(this,c);}
    public JsonObject snapshot(Minecraft c){return AutomationBridge.nativeMaterialSnapshot(this,c);}
    public boolean busy(){return !closed&&pendingId!=null;}
    public void interrupt(Minecraft c,String reason){AutomationBridge.nativeMaterialInterrupt(this,c,reason);}
    public void finish(Minecraft c,boolean keepGuard){AutomationBridge.nativeMaterialFinish(this,c,keepGuard);}
    public void cancel(Minecraft c,String reason){AutomationBridge.nativeMaterialCancel(this,c,reason);}
    public void safeLogout(Minecraft c,String reason){AutomationBridge.nativeMaterialSafeLogout(this,c,reason);}
}
