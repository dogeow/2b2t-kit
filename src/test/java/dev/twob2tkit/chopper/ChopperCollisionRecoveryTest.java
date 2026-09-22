package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.runtime.engine.BorerFlyPath;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.io.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperCollisionRecoveryTest {
    static Set<BlockPos> solid() throws Exception {
        Set<BlockPos> blocks=new HashSet<>();
        try(var r=new BufferedReader(new InputStreamReader(ChopperCollisionRecoveryTest.class.getResourceAsStream("/chopper-return-collision.txt")))) {
            for(String line:r.lines().toList()) {
                String[] s=line.split(" ");blocks.add(new BlockPos(Integer.parseInt(s[0]),Integer.parseInt(s[1]),Integer.parseInt(s[2])));
            }
        }return blocks;
    }
    static boolean free(Set<BlockPos> blocks,AABB box){
        for(BlockPos b:blocks)if(new AABB(b).intersects(box.deflate(.001)))return false;
        return true;
    }
    @Test void capturedGrassEdgeNeedsOnlyFiveHundredthsOfABlockLift() throws Exception {
        var blocks=solid();Vec3 p=new Vec3(5.4819236766,4.96544,9.3000000119);
        AABB body=new AABB(p.x-.3,p.y,p.z-.3,p.x+.3,p.y+1.8,p.z+.3);Vec3 north=new Vec3(0,0,-.12);
        assertTrue(free(blocks,body));assertFalse(free(blocks,body.expandTowards(north)));
        Vec3 lift=ChopperCollisionRecovery.clearanceLift(north,h->free(blocks,body.expandTowards(0,h,0)),h->free(blocks,body.move(0,h,0).expandTowards(north)));
        assertNotNull(lift);assertEquals(.05,lift.y);
        assertTrue(free(blocks,body.move(lift).expandTowards(north)));
    }
    @Test void liftCannotIgnoreACeilingOrATallWallOrHazards(){
        Vec3 north=new Vec3(0,0,-.2);
        assertNull(ChopperCollisionRecovery.clearanceLift(north,h->false,h->true));
        assertNull(ChopperCollisionRecovery.clearanceLift(north,h->true,h->false));
        assertNull(ChopperCollisionRecovery.clearanceLift(new Vec3(0,-.1,0),h->true,h->true));
    }
    @Test void recordedReturnRouteFitsTheWholeBodyWithTheNewClearance() throws Exception {
        var blocks=solid();
        BorerFlyPath.World world=p->p.getX()>=-1&&p.getX()<=12&&p.getY()>=0&&p.getY()<=12&&p.getZ()>=0&&p.getZ()<=18&&!blocks.contains(p);
        var path=BorerFlyPath.findExact(world,new BlockPos(3,5,14),new BlockPos(7,3,4),24,12000);
        assertFalse(path.nodes().isEmpty());
        Vec3 position=new Vec3(3.5,5.12,14.5);
        for(BlockPos node:path.nodes()){
            Vec3 target=BorerFlyPath.waypoint(node);
            int tick=0;
            while(position.distanceTo(target)>.075&&tick++<100){
                var input=BorerFlyPath.input(position,target,0);
                if(input.speed()==0)break;
                AABB body=new AABB(position.x-.3,position.y,position.z-.3,position.x+.3,position.y+1.8,position.z+.3);
                assertTrue(free(blocks,body.expandTowards(input.delta())),"collision moving "+position+" to "+node);
                position=position.add(input.delta());
            }
            assertTrue(tick<100);assertTrue(position.distanceTo(target)<.12);
        }
    }
}
