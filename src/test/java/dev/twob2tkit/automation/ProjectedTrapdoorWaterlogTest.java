package dev.twob2tkit.automation;
import com.google.gson.JsonParser;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.*;
import net.minecraft.world.level.material.Fluids;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.util.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
final class ProjectedTrapdoorWaterlogTest {
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    private final ProjectedTrapdoorRowPolicy.Bounds bounds=new ProjectedTrapdoorRowPolicy.Bounds(100,65,200,128);
    private static ProjectedTrapdoorRowPolicy.Cell good(){return new ProjectedTrapdoorRowPolicy.Cell(true,true,true,true,true,true,true);}
    @Test void exactly29CellsAndMatchingIndexAreRequired(){
        assertNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),0,true,true,true,true));
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(new ProjectedTrapdoorRowPolicy.Bounds(100,65,200,129),Collections.nCopies(29,good()),0,true,true,true,true));
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(28,good()),0,true,true,true,true));
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),29,true,true,true,true));
    }
    @Test void everySealExistingSourceAndControlWireMustRemainValid(){
        for(int field=0;field<7;field++){
            boolean[] v={true,true,true,true,true,true,true};v[field]=false;var cells=new ArrayList<>(Collections.nCopies(29,good()));cells.set(14,new ProjectedTrapdoorRowPolicy.Cell(v[0],v[1],v[2],v[3],v[4],v[5],v[6]));
            assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,cells,0,true,true,true,true),"field"+field);
        }
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),0,true,true,true,false));
    }
    @Test void AlreadyWetTargetIsSkippedButUnchangedDryMayWaitForItsPacket(){
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),0,true,false,true,true));
        assertNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),0,false,true,true,true));
        assertNotNull(ProjectedTrapdoorRowPolicy.rejection(bounds,Collections.nCopies(29,good()),0,false,false,false,true));
    }
    @Test void exclusivePlaceOnly(){
        assertTrue(ProjectedTrapdoorRowPolicy.exclusive(true,false,false,false,false,false,false));
        assertFalse(ProjectedTrapdoorRowPolicy.exclusive(false,false,false,false,false,false,false));
        for(int i=0;i<6;i++){boolean[] v=new boolean[6];v[i]=true;assertFalse(ProjectedTrapdoorRowPolicy.exclusive(true,v[0],v[1],v[2],v[3],v[4],v[5]));}
    }
    @Test void explicitBooleanRequired(){
        assertFalse(ProjectedTrapdoorWaterlog.requested(JsonParser.parseString("{}").getAsJsonObject()));
        assertTrue(ProjectedTrapdoorWaterlog.requested(JsonParser.parseString("{\"projected_trapdoor_waterlog\":true}").getAsJsonObject()));
        for(String v:new String[]{"1","null","[]","\"true\""})assertThrows(IllegalArgumentException.class,()->ProjectedTrapdoorWaterlog.requested(JsonParser.parseString("{\"projected_trapdoor_waterlog\":"+v+"}").getAsJsonObject()));
    }
    @Test void onlyWaterBitMayChangeOnClosedUnpoweredBottomSpruce(){
        var dry=Blocks.SPRUCE_TRAPDOOR.defaultBlockState().setValue(TrapDoorBlock.HALF,Half.BOTTOM).setValue(TrapDoorBlock.FACING,net.minecraft.core.Direction.SOUTH);
        var wet=dry.setValue(TrapDoorBlock.WATERLOGGED,true);assertTrue(ProjectedTrapdoorWaterlog.pair(wet,dry));
        assertFalse(ProjectedTrapdoorWaterlog.pair(wet,dry.cycle(TrapDoorBlock.FACING)));
        assertFalse(ProjectedTrapdoorWaterlog.pair(wet.setValue(TrapDoorBlock.OPEN,true),dry.setValue(TrapDoorBlock.OPEN,true)));
        assertFalse(ProjectedTrapdoorWaterlog.pair(wet.setValue(TrapDoorBlock.HALF,Half.TOP),dry.setValue(TrapDoorBlock.HALF,Half.TOP)));
        assertFalse(ProjectedTrapdoorWaterlog.pair(wet.setValue(TrapDoorBlock.POWERED,true),dry.setValue(TrapDoorBlock.POWERED,true)));
        assertFalse(ProjectedTrapdoorWaterlog.pair(wet,wet));
    }
    @Test void inwardTopSlabCannotAcceptFlowingWaterAndIsRequiredDry(){
        var slab=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE,SlabType.TOP);
        var container=(LiquidBlockContainer)slab.getBlock();
        assertFalse(container.canPlaceLiquid(null,null,null,slab,Fluids.FLOWING_WATER));
        assertTrue(container.canPlaceLiquid(null,null,null,slab,Fluids.WATER));
    }
    @Test void nativeWaterlogStillUsesOneBucketAndItsIndependentPacketReceipts()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/BucketWaterAction.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var hole=node.methods.stream().filter(m->m.name.equals("boundedHole")).findFirst().orElseThrow();
        assertTrue(java.util.stream.StreamSupport.stream(hole.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.owner.endsWith("ProjectedTrapdoorWaterlog")&&c.name.equals("require")));
        var packet=node.methods.stream().filter(m->m.name.equals("serverBlock")).findFirst().orElseThrow();
        assertTrue(java.util.stream.StreamSupport.stream(packet.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.owner.endsWith("ProjectedTrapdoorWaterlog")&&c.name.equals("expectedPacket")));
        var use=node.methods.stream().filter(m->m.name.equals("useOnce")).findFirst().orElseThrow();
        assertEquals(1,java.util.stream.StreamSupport.stream(use.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode c&&c.name.equals("useItem")).count());
    }
}
