package dev.twob2tkit.automation;
import com.google.gson.JsonParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.*;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ShortSourceProfileTest {
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void fourRowsAreExplicitWhileTheLegacyBoundsStillRequireNine(){
        var b=new ProjectedSourceColumnPolicy.Bounds(10,59,20,12,62,20);
        assertFalse(b.valid());assertTrue(b.validRows(4));assertFalse(b.validRows(9));assertFalse(b.validRows(5));
        assertTrue(b.containsRows(11,62,20,4));assertFalse(b.containsRows(11,63,20,4));assertFalse(b.contains(11,62,20));
        assertEquals(9,ProjectedSourceColumnGuard.profileRows(JsonParser.parseString("{}").getAsJsonObject()));
        assertEquals(4,ProjectedSourceColumnGuard.profileRows(JsonParser.parseString("{\"source_column_profile\":\"four_rows\"}").getAsJsonObject()));
        for(String v:List.of("null","true","4","\"four\"","[]"))assertThrows(RuntimeException.class,()->ProjectedSourceColumnGuard.profileRows(JsonParser.parseString("{\"source_column_profile\":"+v+"}").getAsJsonObject()));
    }
    private static List<ProjectedSourceColumnPolicy.Cell> complete(){return new ArrayList<>(Collections.nCopies(12,new ProjectedSourceColumnPolicy.Cell(0,0,true)));}
    @Test void all12CellsAnd35FloorWallPinsRemainMandatory(){
        assertNull(ProjectedSourceColumnPolicy.rejection(complete(),0,false,3,32,true,true,false,4));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(complete(),0,false,3,31,true,true,false,4));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(complete(),0,false,3,72,true,true,false,4));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(complete(),0,false,3,32,true,true,false));
        var cells=complete();cells.set(0,new ProjectedSourceColumnPolicy.Cell(0,-1,false));
        assertNull(ProjectedSourceColumnPolicy.rejection(cells,0,true,3,32,true,true,false,4));
        cells.set(7,new ProjectedSourceColumnPolicy.Cell(0,8,true));assertNotNull(ProjectedSourceColumnPolicy.rejection(cells,0,true,3,32,true,true,false,4));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(complete(),0,false,3,32,true,true,true,4));
    }
    @Test void completedShortSupplyMayExcludeOnlyOneMiddleAndPreserveEveryOtherSource(){
        var levels=new ArrayList<>(Collections.nCopies(12,0));levels.set(10,-1);
        assertTrue(SourceColumnSupplyPolicy.completedChamber(levels,10,12));assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,9,12));
        assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,10));levels.set(8,1);assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,10,12));
    }
    @Test void theShortPathTurnsAfterFiveWestStepsWhileLegacyStillTurnsAfterThree(){
        var seen=new HashSet<String>();for(int i=0;i<8;i++)assertTrue(seen.add(ProjectedBentChannelPolicy.dx(i,4)+","+ProjectedBentChannelPolicy.dz(i,4)));
        assertEquals(-5,ProjectedBentChannelPolicy.dx(7,4));assertEquals(2,ProjectedBentChannelPolicy.dz(7,4));
        assertEquals(-3,ProjectedBentChannelPolicy.dx(7));assertEquals(4,ProjectedBentChannelPolicy.dz(7));
        assertThrows(IllegalArgumentException.class,()->ProjectedBentChannelPolicy.dx(7,5));
    }
    @Test void onlyTheRealBottomRoofOrItsPinnedAirOpeningIsAccepted(){
        var bottom=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE,SlabType.BOTTOM);
        assertTrue(ProjectedBentChannelGuard.shortRoof(bottom,bottom,false));assertTrue(ProjectedBentChannelGuard.shortRoof(bottom,Blocks.AIR.defaultBlockState(),true));
        assertFalse(ProjectedBentChannelGuard.shortRoof(bottom,Blocks.AIR.defaultBlockState(),false));
        assertFalse(ProjectedBentChannelGuard.shortRoof(bottom,bottom,true));
        assertFalse(ProjectedBentChannelGuard.shortRoof(bottom.setValue(SlabBlock.TYPE,SlabType.TOP),Blocks.AIR.defaultBlockState(),true));
        assertFalse(ProjectedBentChannelGuard.shortRoof(bottom,bottom.setValue(SlabBlock.WATERLOGGED,true),false));
    }
    @Test void originalStairSideMustHaveTheFullInwardFaceAndRemainDry(){
        var stairs=Blocks.COBBLESTONE_STAIRS.defaultBlockState().setValue(StairBlock.FACING,Direction.SOUTH).setValue(StairBlock.HALF,Half.BOTTOM).setValue(StairBlock.SHAPE,StairsShape.STRAIGHT);
        assertTrue(ProjectedBentChannelGuard.shortSide(stairs,null,BlockPos.ZERO,Direction.SOUTH));
        assertFalse(ProjectedBentChannelGuard.shortSide(stairs,null,BlockPos.ZERO,Direction.NORTH));
        assertFalse(ProjectedBentChannelGuard.shortSide(stairs.setValue(StairBlock.WATERLOGGED,true),null,BlockPos.ZERO,Direction.SOUTH));
        assertFalse(ProjectedBentChannelGuard.shortSide(stairs.setValue(StairBlock.HALF,Half.TOP),null,BlockPos.ZERO,Direction.SOUTH));
        assertTrue(ProjectedBentChannelGuard.shortSide(Blocks.COBBLESTONE.defaultBlockState(),null,BlockPos.ZERO,Direction.NORTH));
        assertFalse(ProjectedBentChannelGuard.shortSide(Blocks.WATER.defaultBlockState(),null,BlockPos.ZERO,Direction.NORTH));
    }
    @Test void stagedCollectionCanNeverCollectTheOriginalSourceOrConfuseTheTwoSeedPhases(){
        var goal=List.of(0,1,2,3,4,5,6,7);var first=List.of(0,0,0,1,2,3,4,5);var second=List.of(0,0,1,2,3,4,5,6);
        assertTrue(ProjectedBentChannelPolicy.collectLevels(goal,first,2,true));assertFalse(ProjectedBentChannelPolicy.collectLevels(goal,second,2,true));
        assertTrue(ProjectedBentChannelPolicy.collectLevels(goal,second,1,true));assertFalse(ProjectedBentChannelPolicy.collectLevels(goal,first,1,true));
        assertTrue(ProjectedBentChannelPolicy.collectLevels(goal,goal,1,false));assertFalse(ProjectedBentChannelPolicy.collectLevels(goal,first,0,true));
        for(String v:List.of("0","3","1.5","\"2\"","null","true"))assertThrows(RuntimeException.class,()->ProjectedBentChannelGuard.collectionIndex(JsonParser.parseString("{\"projected_bent_channel_collect_index\":"+v+"}").getAsJsonObject()));
        assertEquals(2,ProjectedBentChannelGuard.collectionIndex(JsonParser.parseString("{\"projected_bent_channel_collect_index\":2}").getAsJsonObject()));
    }
    @Test void nativeOwnerPublishesAndUsesTheNarrowNewProof()throws Exception{
        var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){new ClassReader(in).accept(n,0);}
        var owner=n.methods.stream().filter(m->m.name.equals("bucketOwnerCurrent")).findFirst().orElseThrow();
        assertTrue(java.util.stream.StreamSupport.stream(owner.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.owner.endsWith("ProjectedBentChannelGuard")&&c.name.equals("shieldedWorkspace")));
        var snapshot=n.methods.stream().filter(m->m.name.equals("snapshot")).findFirst().orElseThrow();
        for(String protocol:List.of("projected_short_source_profile_protocol","projected_bent_collection_protocol"))assertTrue(java.util.stream.StreamSupport.stream(snapshot.instructions.spliterator(),false).anyMatch(i->i instanceof LdcInsnNode c&&protocol.equals(c.cst)));
    }
}
