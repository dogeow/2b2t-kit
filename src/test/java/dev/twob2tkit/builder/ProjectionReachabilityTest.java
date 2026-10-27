package dev.twob2tkit.builder;

import java.util.ArrayList;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionReachabilityTest {
    @Test void hostKeepsReachAndBodyChecksBeforeSampledVisibility() throws Exception {
        var type=new org.objectweb.asm.tree.ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/builder/ProjectionBuildJob.class")) {
            assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(type,0);
        }
        var method=type.methods.stream().filter(m->m.name.equals("reachable")).findFirst().orElseThrow();
        int index=0,distance=-1,body=-1,samples=-1;
        for(var instruction:method.instructions) {
            if(instruction instanceof org.objectweb.asm.tree.MethodInsnNode call) {
                if(call.name.equals("distanceTo"))distance=index;
                if(call.name.equals("intersects"))body=index;
                if(call.owner.endsWith("/ProjectionReachability")&&call.name.equals("reachable"))samples=index;
            }
            index++;
        }
        assertTrue(distance>=0&&body>distance&&samples>body);
    }
    @Test void overhangMayHideTheCentreWhileLeavingTheNormalWestFaceReachable() {
        var eye=new Vec3(761425.5,64.64,793988.5);
        var target=new BlockPos(761426,63,793988);
        var overhang=new AABB(761426,64,793988,761427,65,793989);
        assertTrue(overhang.clip(eye,Vec3.atCenterOf(target)).isPresent());
        assertTrue(ProjectionReachability.visible(eye,target,4.15,
            point->overhang.clip(eye,point).isEmpty()));
    }
    @Test void opaqueWallNeverBecomesReachableBySamplingMorePoints() {
        var eye=new Vec3(-1,.5,.5);var target=BlockPos.ZERO;
        var wall=new AABB(-.1,-2,-2,-.01,3,3);
        assertFalse(ProjectionReachability.visible(eye,target,4.15,
            point->wall.clip(eye,point).isEmpty()));
    }
    @Test void everyProbeStaysInsideTheExactTargetAndNormalReach() {
        var eye=new Vec3(-1,.5,.5);var seen=new ArrayList<Vec3>();
        assertFalse(ProjectionReachability.visible(eye,BlockPos.ZERO,4.15,point->{seen.add(point);return false;}));
        assertEquals(new Vec3(.5,.5,.5),seen.getFirst());assertEquals(55,seen.size());
        for(var p:seen)assertTrue(p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.z>0&&p.z<1);
        assertFalse(ProjectionReachability.visible(new Vec3(-10,.5,.5),BlockPos.ZERO,4.15,p->true));
    }
    @Test void invalidGeometryAndBlockedRaysDoNotAdmitPlacement() {
        assertFalse(ProjectionReachability.visible(new Vec3(Double.NaN,0,0),BlockPos.ZERO,4.15,p->true));
        assertFalse(ProjectionReachability.visible(Vec3.ZERO,BlockPos.ZERO,Double.POSITIVE_INFINITY,p->true));
        assertFalse(ProjectionReachability.visible(Vec3.ZERO,BlockPos.ZERO,0,p->true));
        assertFalse(ProjectionReachability.visible(Vec3.ZERO,BlockPos.ZERO,4.15,p->false));
    }
}
