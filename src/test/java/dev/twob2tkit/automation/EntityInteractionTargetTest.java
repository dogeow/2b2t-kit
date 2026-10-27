package dev.twob2tkit.automation;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.Shapes;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EntityInteractionTargetTest {
    private static Predicate<Vec3> window(Vec3 eye){
        var lower=Shapes.block();
        var upper=Shapes.box(0,.5,0,1,1,1);
        return point->lower.clip(eye,point,BlockPos.ZERO)==null
            &&upper.clip(eye,point,new BlockPos(0,1,0))==null;
    }
    @Test void bodyCanBeClickedThroughTheFixedWindowWhenTheEyesAreHidden()throws Exception{
        var expectedArtifact=System.getProperty("expected.host.patch");
        if(expectedArtifact!=null)assertEquals(java.nio.file.Path.of(expectedArtifact).toRealPath(),
            java.nio.file.Path.of(EntityInteractionTarget.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath());
        var eye=new Vec3(.5,1.62,2);
        var body=new AABB(.2,0,-.8,.8,1.95,-.2);
        assertNotNull(Shapes.box(0,.5,0,1,1,1)
            .clip(eye,new Vec3(.5,1.62,-.5),new BlockPos(0,1,0)));
        var selection=EntityInteractionTarget.find(body,eye,3,window(eye));
        assertNotNull(selection.hit());assertTrue(selection.inRange());
        assertTrue(body.contains(selection.hit()));assertTrue(window(eye).test(selection.hit()));
    }
    @Test void raisedBedOccupantUsesAReachableVisibleBodyPartNotItsHiddenCentre(){
        var eye=new Vec3(.5,1.62,1.7);
        var body=new AABB(.2,.5625,-1.8,.8,2.5125,-1.2);
        var oldCentre=new Vec3(.5,.5625+1.95*.55,-1.5);
        assertTrue(eye.distanceTo(oldCentre)>3);
        var selection=EntityInteractionTarget.find(body,eye,3,window(eye));
        assertNotNull(selection.hit());assertTrue(body.contains(selection.hit()));
        assertTrue(eye.distanceTo(selection.hit())<=3);
        assertTrue(selection.hit().y<1.5);assertTrue(window(eye).test(selection.hit()));
    }
    @Test void solidWallsStillRejectEveryBodyPart(){
        var eye=new Vec3(.5,1.62,2);
        var body=new AABB(.2,0,-.8,.8,1.95,-.2);
        var wall=Shapes.block();
        var selection=EntityInteractionTarget.find(body,eye,3,p->
            wall.clip(eye,p,BlockPos.ZERO)==null&&wall.clip(eye,p,new BlockPos(0,1,0))==null);
        assertNull(selection.hit());assertTrue(selection.inRange());
    }
    @Test void distanceIsCheckedBeforeVisibilityAndNoPointLeavesTheBody(){
        var calls=new AtomicInteger();var body=new AABB(0,0,10,1,2,11);
        var far=EntityInteractionTarget.find(body,new Vec3(.5,1.62,0),3,p->{calls.incrementAndGet();return true;});
        assertNull(far.hit());assertFalse(far.inRange());assertEquals(0,calls.get());
        var eye=new Vec3(.5,1.62,9);
        var blocked=EntityInteractionTarget.find(body,eye,3,p->{
            assertTrue(body.contains(p));assertTrue(eye.distanceTo(p)<=3);return false;
        });
        assertNull(blocked.hit());assertTrue(blocked.inRange());
    }
    @Test void invalidGeometryNeverProducesAnInteraction(){
        var body=new AABB(0,0,0,1,2,1);var eye=new Vec3(.5,1.62,3);
        assertThrows(IllegalArgumentException.class,()->EntityInteractionTarget.find(body,eye,Double.NaN,p->true));
        assertThrows(IllegalArgumentException.class,()->EntityInteractionTarget.find(body,new Vec3(Double.NaN,1,3),3,p->true));
        assertThrows(IllegalArgumentException.class,()->EntityInteractionTarget.find(new AABB(0,0,0,0,2,1),eye,3,p->true));
    }
}
