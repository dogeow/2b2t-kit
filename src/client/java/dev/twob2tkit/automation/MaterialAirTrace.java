package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import java.lang.reflect.Field;
import java.util.ArrayDeque;

/** Bounded, read-only evidence around restored Flight; never changes movement or settings. */
final class MaterialAirTrace {
    static final int LIMIT=128;
    private final ArrayDeque<JsonObject> frames=new ArrayDeque<>();
    void add(JsonObject frame){
        if(frames.size()==LIMIT)frames.removeFirst();
        frames.addLast(frame.deepCopy());
    }
    JsonArray snapshot(){
        var out=new JsonArray();for(var frame:frames)out.add(frame.deepCopy());return out;
    }
    void record(Minecraft c,String stage,boolean restored,int restorations){
        if(c.player==null||c.options==null)return;
        var p=c.player;var row=new JsonObject();row.addProperty("tick",p.tickCount);
        row.addProperty("stage",stage);row.addProperty("restored",restored);row.addProperty("restorations",restorations);
        row.add("position",vector(p.getX(),p.getY(),p.getZ()));
        var velocity=p.getDeltaMovement();row.add("velocity",vector(velocity.x,velocity.y,velocity.z));
        row.addProperty("yaw",p.getYRot());row.addProperty("pitch",p.getXRot());
        row.addProperty("sprinting",p.isSprinting());row.addProperty("on_ground",p.onGround());
        row.addProperty("horizontal_collision",p.horizontalCollision);row.addProperty("vertical_collision",p.verticalCollision);
        row.addProperty("under_water",p.isUnderWater());row.addProperty("health",p.getHealth());
        row.addProperty("hurt_time",p.hurtTime);
        row.addProperty("key_bits",bits(c.options.keyUp.isDown(),c.options.keyDown.isDown(),
            c.options.keyLeft.isDown(),c.options.keyRight.isDown(),c.options.keyJump.isDown(),
            c.options.keyShift.isDown(),c.options.keySprint.isDown()));
        if(p.input!=null){var input=p.input.keyPresses;
            row.addProperty("sampled_input_bits",bits(input.forward(),input.backward(),input.left(),input.right(),input.jump(),input.shift(),input.sprint()));
            var v=p.input.getMoveVector();row.add("sampled_move",vector(v.x,0,v.y));
        }
        row.add("flight",flightState(module("meteordevelopment.meteorclient.systems.modules.movement.Flight")));
        add(row);
    }
    static int bits(boolean forward,boolean back,boolean left,boolean right,boolean jump,boolean shift,boolean sprint){
        return(forward?1:0)|(back?2:0)|(left?4:0)|(right?8:0)|(jump?16:0)|(shift?32:0)|(sprint?64:0);
    }
    private static JsonArray vector(double x,double y,double z){var a=new JsonArray();a.add(x);a.add(y);a.add(z);return a;}
    static JsonObject flightState(Object module){
        var out=new JsonObject();out.addProperty("available",module!=null);if(module==null)return out;
        try{out.addProperty("active",Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module)));}
        catch(ReflectiveOperationException|RuntimeException ignored){out.addProperty("active_unavailable",true);}
        for(String name:new String[]{"mode","speed","verticalSpeedMatch","noSneak","antiKickMode","delayLeft","offLeft"}){
            try{
                Field field=module.getClass().getDeclaredField(name);field.setAccessible(true);Object value=field.get(module);
                if(!(value instanceof Number)&&!(value instanceof Boolean)&&!(value instanceof Enum<?>))
                    value=value.getClass().getMethod("get").invoke(value);
                if(value instanceof Number n)out.addProperty(name,n);
                else if(value instanceof Boolean b)out.addProperty(name,b);
                else if(value instanceof Enum<?> e)out.addProperty(name,e.name());
                else out.addProperty(name,"unsupported");
            }catch(ReflectiveOperationException|RuntimeException ignored){out.addProperty(name,"unavailable");}
        }return out;
    }
    private static Object module(String name){
        try{Class<?> modules=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            Object owner=modules.getMethod("get").invoke(null);
            return owner==null?null:modules.getMethod("get",Class.class).invoke(owner,Class.forName(name));
        }catch(ReflectiveOperationException|LinkageError|RuntimeException absent){return null;}
    }
}
