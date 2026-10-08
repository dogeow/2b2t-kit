package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperLootFlightTest {
    private AABB body(double x,double y,double z){return new AABB(x-.3,y,z-.3,x+.3,y+1.8,z+.3);}
    private AABB item(double x,double y,double z){return new AABB(x-.125,y,z-.125,x+.125,y+.25,z+.125);}
    @Test void capturedTwoAndHalfBlockHorizontalStallIsOutsidePickupBody(){
        assertFalse(ChopperLootFlight.pickupIntersects(body(760867.7,84.975,798010.578),item(760870.029,85,798010.585)));
    }
    @Test void hoveringAWholeBlockAboveDropRequiresControlledDescent(){
        assertFalse(ChopperLootFlight.pickupIntersects(body(0,75.1,0),item(0,74,0)));
        assertTrue(ChopperLootFlight.pickupIntersects(body(0,74.1,0),item(0,74,0)));
    }
    @Test void waypointKeepsFloorMarginWithoutGrowingPastTwoBlockTunnel(){
        Vec3 point=ChopperLootFlight.feet(new BlockPos(0,74,0));
        assertEquals(74.1,point.y,1e-6);assertTrue(point.y+1.81<76);
    }
    @Test void removedOrMergedEntityWithoutInventoryGainDoesNotCountAsPickup(){
        assertEquals(0,ChopperLootPolicy.verifiedPickupGain(32,32,3));
        assertEquals(0,ChopperLootPolicy.verifiedPickupGain(32,31,3));
        assertEquals(2,ChopperLootPolicy.verifiedPickupGain(32,34,3));
        assertEquals(3,ChopperLootPolicy.verifiedPickupGain(32,40,3));
    }
    @Test void capturedSmallFloorPenetrationCanOnlyLiftPastAThinFloor(){
        var current=body(0,84.975,0);
        assertTrue(ChopperLootFlight.thinFloorOverlap(current,java.util.List.of(new AABB(-1,84,-1,1,85,1))));
        assertFalse(ChopperLootFlight.thinFloorOverlap(current,java.util.List.of(new AABB(-1,84,-1,1,86,1))));
        assertFalse(ChopperLootFlight.thinFloorOverlap(current,java.util.List.of()));
    }
    @Test void sharedSearchRoutesAroundWallWithOnlyExecutableSingleAxisEdges(){
        var navigation=new dev.twob2tkit.runtime.engine.DefaultBuildNavigation();
        var world=new dev.twob2tkit.runtime.api.BuildNavigation.World(){
            public boolean clear(BlockPos p){return p.getX()>=0&&p.getX()<=3&&p.getY()>=74&&p.getY()<=75
                &&p.getZ()>=0&&p.getZ()<=2&&!(p.getX()==1&&p.getZ()==0);}
            public boolean edge(BlockPos a,BlockPos b){return ChopperLootFlight.adjacentEdge(a,b);}
        };
        var search=navigation.search(world,new BlockPos(0,74,0),java.util.List.of(new BlockPos(3,74,0)));
        dev.twob2tkit.runtime.api.BuildNavigation.Result result=null;
        for(int i=0;i<100&&result==null;i++)result=search.advance(256,Long.MAX_VALUE);
        assertNotNull(result);assertFalse(result.nodes().isEmpty());
        assertTrue(result.nodes().stream().anyMatch(p->p.getZ()>0));
        for(int i=1;i<result.nodes().size();i++)assertEquals(1,result.nodes().get(i-1).distManhattan(result.nodes().get(i)));
    }
}
