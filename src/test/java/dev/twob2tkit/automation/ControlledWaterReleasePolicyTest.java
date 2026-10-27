package dev.twob2tkit.automation;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ControlledWaterReleasePolicyTest {
    private static ControlledWaterReleasePolicy.Cell p(int x,int y,int z){return new ControlledWaterReleasePolicy.Cell(x,y,z);}
    private final ControlledWaterReleasePolicy.Bounds box=new ControlledWaterReleasePolicy.Bounds(p(0,0,0),p(4,3,4));
    private final ControlledWaterReleasePolicy.Cell target=p(2,1,2);
    private static final class Room implements ControlledWaterReleasePolicy.World {
        Set<ControlledWaterReleasePolicy.Cell> walls=new HashSet<>(),water=new HashSet<>(),gates=new HashSet<>(),lava=new HashSet<>(),containers=new HashSet<>(),entities=new HashSet<>(),unloaded=new HashSet<>(),decorations=new HashSet<>();
        Room(){
            for(int x=0;x<=4;x++)for(int z=0;z<=4;z++)walls.add(p(x,0,z));
            for(int y=1;y<=3;y++)for(int n=0;n<=4;n++){walls.add(p(0,y,n));walls.add(p(4,y,n));walls.add(p(n,y,0));walls.add(p(n,y,4));}
            walls.add(p(2,1,2));water.add(p(1,1,2));water.add(p(3,1,2));
        }
        public boolean loaded(ControlledWaterReleasePolicy.Cell p){return !unloaded.contains(p);}
        public boolean barrier(ControlledWaterReleasePolicy.Cell p){return walls.contains(p)||gates.contains(p);}
        public boolean air(ControlledWaterReleasePolicy.Cell p){return !barrier(p)&&!water.contains(p)&&!lava.contains(p)&&!containers.contains(p)&&!decorations.contains(p);}
        public boolean water(ControlledWaterReleasePolicy.Cell p){return water.contains(p);}
        public boolean otherFluid(ControlledWaterReleasePolicy.Cell p){return lava.contains(p);}
        public boolean container(ControlledWaterReleasePolicy.Cell p){return containers.contains(p);}
        public boolean living(ControlledWaterReleasePolicy.Cell p){return entities.contains(p);}
    }
    private String check(Room r){return ControlledWaterReleasePolicy.rejection(r,box,target,true,true);}
    @Test void onlyTheDeclaredRetainerIsSimulatedAsRemovedInsideAClosedBasin(){assertNull(check(new Room()));}
    @Test void aMissingFloorOrSideWallIsNotAnEnclosure(){
        var floor=new Room();floor.walls.remove(p(2,0,2));assertNotNull(check(floor));
        var side=new Room();side.walls.remove(p(0,1,2));assertNotNull(check(side));
    }
    @Test void aPlainWaterBlockingGateCanCloseTheFlowPathWithoutBlockingMobs(){
        var r=new Room();r.walls.remove(p(0,1,2));r.gates.add(p(0,1,2));assertNull(check(r));r.gates.clear();assertNotNull(check(r));
    }
    @Test void unloadedCellsContainersOtherFluidsAndLivingEntitiesCannotBeAssumedSafe(){
        var unloaded=new Room();unloaded.unloaded.add(p(3,1,2));assertNotNull(check(unloaded));
        var container=new Room();container.containers.add(p(1,1,1));assertNotNull(check(container));
        var lava=new Room();lava.water.remove(p(1,1,2));lava.lava.add(p(1,1,2));assertNotNull(check(lava));
        var living=new Room();living.entities.add(p(3,1,2));assertNotNull(check(living));
        var decor=new Room();decor.decorations.add(p(1,1,1));assertNotNull(check(decor));
    }
    @Test void requestCannotClaimAnUnownedLargeOrBoundaryRelease(){
        var r=new Room();assertNotNull(ControlledWaterReleasePolicy.rejection(r,box,target,false,true));assertNotNull(ControlledWaterReleasePolicy.rejection(r,box,target,true,false));
        assertNotNull(ControlledWaterReleasePolicy.rejection(r,new ControlledWaterReleasePolicy.Bounds(p(0,0,0),p(100,3,4)),target,true,true));
        assertNotNull(ControlledWaterReleasePolicy.rejection(r,box,p(0,1,2),true,true));r.water.clear();assertNotNull(check(r));
    }
    @Test void anUpperSourceMustAlsoBeContained(){
        var r=new Room();r.water.add(p(2,2,2));r.walls.remove(p(4,2,2));assertNotNull(check(r));
    }
    @Test void waterRefillStillNeedsBothServerEvidenceAndTheNativeSequenceAck(){
        var proof=new SingleBlockServerConfirmation<String,String>();proof.begin("world","release","cell",s->SingleBlockRemovalPolicy.removed(s.equals("air"),s.equals("water"),false,true));proof.sent("world","release","cell",9);
        proof.clientState("world","release","cell","water");assertFalse(proof.confirmed("world","release","cell","water",false));
        proof.serverBlock("world","release","cell","water");assertFalse(proof.confirmed("world","release","cell","water",false));proof.serverAck("world","release","cell",8);assertFalse(proof.confirmed("world","release","cell","water",false));proof.serverAck("world","release","cell",9);assertFalse(proof.confirmed("world","release","cell","water",true));assertTrue(proof.confirmed("world","release","cell","water",false));
        assertFalse(SingleBlockRemovalPolicy.removed(false,true,false));assertTrue(SingleBlockRemovalPolicy.removed(false,true,false,true));assertFalse(SingleBlockRemovalPolicy.removed(false,false,false,true));
    }
}
