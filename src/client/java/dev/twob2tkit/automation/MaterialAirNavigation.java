package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import net.minecraft.client.Minecraft;
import net.minecraft.world.phys.Vec3;

/** Brake and settle an owned air-only route using normal Meteor Flight and input. */
final class MaterialAirNavigation {
    private final Vec3 target;
    private final double arrival;
    private final MaterialAirArrivalPolicy.Settlement settlement;
    private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private Vec3 previous,displacement=Vec3.ZERO;
    private RotationAim.Look look;
    private boolean precise,closed;
    MaterialAirNavigation(Vec3 target,double arrival){this.target=target;this.arrival=arrival;settlement=new MaterialAirArrivalPolicy.Settlement(arrival);}

    private void precision(Minecraft c){
        KitClient.controller().stop(c,"材料航点精确停靠");
        release(c);
        flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/material-air-flight-speed.bak"));
        String error=flight.acquire(c.player);
        if(error!=null)throw new IllegalStateException(error);
        flight.hover();precise=true;settlement.precision();previous=null;
    }
    boolean input(Minecraft c){
        if(closed||settlement.done())return false;
        var error=target.subtract(c.player.position());
        if(!precise){
            if(!MaterialAirArrivalPolicy.takeOver(error,c.player.getDeltaMovement(),KitClient.controller().isActive()))return false;
            precision(c);
        }
        release(c);look=null;
        if(settlement.restored())return true;
        String failure=flight.acquire(c.player);
        if(failure!=null)throw new IllegalStateException(failure);
        var motion=MaterialAirArrivalPolicy.motion(error);
        if(!motion.moving()){flight.hover();return true;}
        flight.speed(motion.speed());
        if(motion.vertical()){c.options.keyJump.setDown(error.y>0);c.options.keyShift.setDown(error.y<0);}
        if(motion.horizontal()){
            look=new RotationAim.Look(RotationAim.yawToward(error.x,error.z),0);
            RotationAim.apply(c.player,look);c.options.keyUp.setDown(true);
        }
        return true;
    }
    void observe(Minecraft c){
        if(closed||settlement.done())return;
        if(!precise){
            if(KitClient.controller().isActive())return;
            precision(c);
        }
        Vec3 now=c.player.position(),error=target.subtract(now);
        if(previous==null){previous=now;return;}
        displacement=now.subtract(previous);previous=now;
        switch(settlement.observe(error,displacement,c.player.getDeltaMovement())){
            case RESTORE -> {
                release(c);look=null;flight.hover();flight.closeKeepingFlight();
            }
            case REACQUIRE -> precision(c);
            default -> {}
        }
    }
    void pause(Minecraft c){
        settlement.pause();previous=null;release(c);look=null;
        if(precise&&!settlement.restored())flight.hover();
    }
    void defensePause(){settlement.pause();previous=null;}
    boolean reapply(Minecraft c){
        if(closed||settlement.restored()||look==null||c.player==null)return false;
        RotationAim.apply(c.player,look);return true;
    }
    boolean done(){return settlement.done();}
    JsonObject snapshot(Minecraft c){
        var result=new JsonObject();result.addProperty("phase",settlement.done()?"confirmed":settlement.restored()?"checking_restored_flight":precise?"precise_braking":"cruising");
        result.addProperty("arrival",arrival);result.addProperty("stable_ticks",settlement.stableTicks());
        result.addProperty("restored_ticks",settlement.restoredTicks());result.addProperty("restorations",settlement.restorations());
        result.addProperty("observed_step",displacement.length());
        if(c.player!=null){var error=target.subtract(c.player.position());
            result.addProperty("horizontal_error",Math.hypot(error.x,error.z));result.addProperty("vertical_error",Math.abs(error.y));
            var velocity=c.player.getDeltaMovement();result.addProperty("horizontal_velocity",Math.hypot(velocity.x,velocity.z));
            result.addProperty("vertical_velocity",velocity.y);}
        return result;
    }
    void close(Minecraft c){
        if(closed)return;closed=true;release(c);look=null;
        flight.closeKeepingFlight();
    }
    private static void release(Minecraft c){
        if(c.options==null)return;
        for(var key:new net.minecraft.client.KeyMapping[]{c.options.keyUp,c.options.keyDown,c.options.keyLeft,
                c.options.keyRight,c.options.keyJump,c.options.keyShift,c.options.keySprint})key.setDown(false);
    }
}
