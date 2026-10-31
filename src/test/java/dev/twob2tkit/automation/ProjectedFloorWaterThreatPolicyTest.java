package dev.twob2tkit.automation;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedFloorWaterThreatPolicyTest {
    @org.junit.jupiter.api.BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void topSlabActuallySealsItsUpperFaceButBottomSlabAndHeatDoNot(){
        var top=net.minecraft.world.level.block.Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(net.minecraft.world.level.block.SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.TOP);
        assertTrue(ProjectedFloorWaterGuard.floorSeal(top,null,net.minecraft.core.BlockPos.ZERO));
        assertTrue(ProjectedFloorWaterGuard.floorSeal(top.setValue(net.minecraft.world.level.block.SlabBlock.WATERLOGGED,true),null,net.minecraft.core.BlockPos.ZERO));
        assertFalse(ProjectedFloorWaterGuard.floorSeal(top.setValue(net.minecraft.world.level.block.SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.BOTTOM),null,net.minecraft.core.BlockPos.ZERO));
        assertTrue(ProjectedFloorWaterGuard.floorSeal(net.minecraft.world.level.block.Blocks.DIRT.defaultBlockState(),null,net.minecraft.core.BlockPos.ZERO));
        assertFalse(ProjectedFloorWaterGuard.floorSeal(net.minecraft.world.level.block.Blocks.MAGMA_BLOCK.defaultBlockState(),null,net.minecraft.core.BlockPos.ZERO));
        assertFalse(ProjectedFloorWaterGuard.floorSeal(net.minecraft.world.level.block.Blocks.AIR.defaultBlockState(),null,net.minecraft.core.BlockPos.ZERO));
    }
    private static ProjectedFloorWaterThreatPolicy.Threat below(){return new ProjectedFloorWaterThreatPolicy.Threat(true,true,false,57.95);}
    @Test void ordinarySpidersRemainSubjectToTheSamePhysicalFloorProof(){
        assertTrue(ProjectedFloorWaterGuard.supportedGroundMob("minecraft:spider"));
        assertTrue(ProjectedFloorWaterGuard.supportedGroundMob("minecraft:cave_spider"));
        for(String type:List.of("minecraft:creeper","minecraft:enderman","minecraft:blaze","minecraft:ghast","minecraft:wither"))assertFalse(ProjectedFloorWaterGuard.supportedGroundMob(type));
        assertFalse(ProjectedFloorWaterThreatPolicy.permit(true,false,true,true,true,65,List.of(below())));
    }
    @Test void recordedUndergroundZombiesAreSeparatedByTheActualFloor(){assertTrue(ProjectedFloorWaterThreatPolicy.permit(true,true,true,true,true,62,List.of(below(),new ProjectedFloorWaterThreatPolicy.Threat(true,true,false,48.74))));}
    @Test void noPhysicalProofMayBeMissing(){for(int i=0;i<5;i++){boolean[] a={true,true,true,true,true};a[i]=false;assertFalse(ProjectedFloorWaterThreatPolicy.permit(a[0],a[1],a[2],a[3],a[4],62,List.of(below())));}}
    @Test void sameFloorVisibleCreeperUnknownOrStaleEnemyAlwaysBlocks(){for(var t:List.of(new ProjectedFloorWaterThreatPolicy.Threat(true,true,false,62.01),new ProjectedFloorWaterThreatPolicy.Threat(true,true,true,56),new ProjectedFloorWaterThreatPolicy.Threat(true,false,false,56),new ProjectedFloorWaterThreatPolicy.Threat(false,true,false,56),new ProjectedFloorWaterThreatPolicy.Threat(true,true,false,Double.NaN)))assertFalse(ProjectedFloorWaterThreatPolicy.permit(true,true,true,true,true,62,List.of(below(),t)));}
    @Test void absentObservationsFailClosed(){assertFalse(ProjectedFloorWaterThreatPolicy.permit(true,true,true,true,true,62,null));assertFalse(ProjectedFloorWaterThreatPolicy.permit(true,true,true,true,true,62,Arrays.asList((ProjectedFloorWaterThreatPolicy.Threat)null)));}
    @Test void nativeOwnerStillChecksFloorOnEveryUse()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var m=node.methods.stream().filter(v->v.name.equals("bucketOwnerCurrent")).findFirst().orElseThrow();assertTrue(java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.owner.endsWith("ProjectedFloorWaterGuard")&&c.name.equals("shieldedWorkspace")));
    }
}
