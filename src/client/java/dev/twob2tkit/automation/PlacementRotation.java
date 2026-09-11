package dev.twob2tkit.automation;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.network.protocol.game.ServerboundMovePlayerPacket;
import net.minecraft.util.Mth;

/** Share Meteor's rotation ordering instead of racing its movement-packet hooks. */
public final class PlacementRotation {
    private PlacementRotation() {}
    public static void after(Minecraft c,float yaw,float pitch,Runnable action){
        RotationAim.apply(c.player,yaw,pitch);
        try{
            Class<?> type=Class.forName("meteordevelopment.meteorclient.utils.player.Rotations");
            type.getMethod("rotate",double.class,double.class,int.class,boolean.class,Runnable.class).invoke(null,(double)yaw,(double)pitch,50,true,action);
        }catch(ClassNotFoundException absent){
            c.player.connection.send(new ServerboundMovePlayerPacket.Rot(yaw,pitch,c.player.onGround(),c.player.horizontalCollision));
            if(action!=null)action.run();
        }catch(ReflectiveOperationException error){throw new IllegalStateException("Meteor rotation integration failed",error);}
    }
    public static boolean prepare(Minecraft c,float yaw,float pitch){
        after(c,yaw,pitch,null);
        try{
            Class<?> t=Class.forName("meteordevelopment.meteorclient.utils.player.Rotations");
            return Math.abs(Mth.wrapDegrees(t.getField("serverYaw").getFloat(null)-yaw))<1 && Math.abs(t.getField("serverPitch").getFloat(null)-pitch)<1;
        }catch(ClassNotFoundException absent){return true;}catch(ReflectiveOperationException e){return false;}
    }
}
