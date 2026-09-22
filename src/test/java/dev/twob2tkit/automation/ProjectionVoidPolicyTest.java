package dev.twob2tkit.automation;
import net.minecraft.core.BlockPos;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionVoidPolicyTest {
 private Set<BlockPos> box(int x,int y,int z){var cells=new HashSet<BlockPos>();for(var p:BlockPos.betweenClosed(new BlockPos(0,0,0),new BlockPos(x,y,z)))cells.add(p.immutable());return cells;}
 @Test void sealedRoomAirIsDistinctFromExteriorAir(){
  var selected=box(4,4,4);var room=new HashSet<BlockPos>();for(var p:BlockPos.betweenClosed(new BlockPos(1,1,1),new BlockPos(3,3,3)))room.add(p.immutable());
  var air=new HashSet<>(room);air.add(new BlockPos(0,0,0));assertEquals(room,ProjectionVoidPolicy.enclosed(selected,air));
 }
 @Test void anOpeningConnectsTheRoomToExterior(){
  var selected=box(2,2,2);var room=new BlockPos(1,1,1);assertEquals(Set.of(room),ProjectionVoidPolicy.enclosed(selected,Set.of(room)));
  assertTrue(ProjectionVoidPolicy.enclosed(selected,Set.of(room,new BlockPos(0,1,1))).isEmpty());
 }
 @Test void clippedLayersAndStructureVoidsMustNotInventASealedRoom(){
  var selected=box(2,2,2);selected.remove(new BlockPos(1,2,1));assertTrue(ProjectionVoidPolicy.enclosed(selected,Set.of(new BlockPos(1,1,1))).isEmpty());
 }
 @Test void oneOpenRoomDoesNotHideAnotherSealedRoom(){
  var selected=box(4,2,2);var closed=new BlockPos(3,1,1);assertEquals(Set.of(closed),ProjectionVoidPolicy.enclosed(selected,Set.of(new BlockPos(0,1,1),new BlockPos(1,1,1),closed)));
 }
 @Test void missingSelectionCoverageIsRejected(){assertThrows(IllegalArgumentException.class,()->ProjectionVoidPolicy.enclosed(Set.of(),Set.of(BlockPos.ZERO)));}
}
