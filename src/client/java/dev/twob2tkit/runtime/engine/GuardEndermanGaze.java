package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.monster.EnderMan;

/** Normal view input only: keep the shield and unresolved enemies intact. */
final class GuardEndermanGaze {
    private GuardEndermanGaze() {}
    static RotationAim.Look away(Minecraft c){
        var p=c.player;if(p==null)return new RotationAim.Look(0,0);
        var unchanged=new RotationAim.Look(p.getYRot(),p.getXRot());
        if(c.level==null||c.gui.screen()!=null)return unchanged;
        var eye=p.getEyePosition();
        var targets=c.level.getEntities(p,p.getBoundingBox().inflate(40)).stream()
            .filter(e->e instanceof EnderMan&&e.isAlive()&&p.hasLineOfSight(e))
            .map(e->{var v=e.getEyePosition();return new double[]{v.x,v.y,v.z};}).toList();
        var d=GuardEndermanGazePolicy.direction(new double[]{eye.x,eye.y,eye.z},targets);
        return d==null?unchanged:RotationAim.lookAt(p,eye.add(d[0]*8,d[1]*8,d[2]*8));
    }
    static void apply(Minecraft c){if(c.player!=null&&c.gui.screen()==null)RotationAim.apply(c.player,away(c));}
}
