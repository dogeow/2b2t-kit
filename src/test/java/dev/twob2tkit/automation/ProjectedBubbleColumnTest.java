package dev.twob2tkit.automation;
import com.google.gson.JsonParser;
import net.minecraft.core.*;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.Half;
import org.junit.jupiter.api.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedBubbleColumnTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void bottomUpRequiresEveryEarlierBubbleAndUntouchedLaterCell(){
  for(int target=0;target<7;target++){
   var cells=new ArrayList<Integer>();for(int i=0;i<7;i++)cells.add(i<target?1:-1);
   assertTrue(ProjectedBubblePolicy.stage(cells,target,true));assertFalse(ProjectedBubblePolicy.stage(cells,target,false));
   cells.set(target,0);assertFalse(ProjectedBubblePolicy.stage(cells,target,true));assertTrue(ProjectedBubblePolicy.stage(cells,target,false));
   cells.set(target,1);assertTrue(ProjectedBubblePolicy.stage(cells,target,false));
   for(int other=0;other<7;other++)if(other!=target){var bad=new ArrayList<>(cells);bad.set(other,-2);assertFalse(ProjectedBubblePolicy.stage(bad,target,false));}
  }
  assertFalse(ProjectedBubblePolicy.stage(null,0,true));assertFalse(ProjectedBubblePolicy.stage(Collections.nCopies(6,-1),0,true));
 }
 @Test void onlyUpwardBubblesAcknowledgeThePlacedResult(){
  assertTrue(ProjectedBubbleColumnGuard.upward(Blocks.BUBBLE_COLUMN.defaultBlockState().setValue(BubbleColumnBlock.DRAG_DOWN,false)));
  assertFalse(ProjectedBubbleColumnGuard.upward(Blocks.BUBBLE_COLUMN.defaultBlockState().setValue(BubbleColumnBlock.DRAG_DOWN,true)));
  assertFalse(ProjectedBubbleColumnGuard.upward(Blocks.WATER.defaultBlockState()));assertFalse(ProjectedBubbleColumnGuard.upward(Blocks.AIR.defaultBlockState()));
 }
 @Test void exactSevenCellShapeAndIntendedOutletArePinned(){
  var low=new BlockPos(93,63,94);assertTrue(ProjectedBubbleColumnGuard.shape(low,low.above(6),low.above(3)));
  assertFalse(ProjectedBubbleColumnGuard.shape(low,low.above(5),low));assertFalse(ProjectedBubbleColumnGuard.shape(low,low.above(6),low.east()));
  for(int i=1;i<=7;i++){assertEquals(-Math.min(i,6),ProjectedBubblePolicy.outletDx(i));assertEquals(i==7?-1:0,ProjectedBubblePolicy.outletDz(i));}
  assertThrows(IllegalArgumentException.class,()->ProjectedBubblePolicy.outletDx(8));
 }
 @Test void dryOriginalPartialBarriersRejectFlowButOpenWetOrWrongBlocksDoNot(){
  var trap=Blocks.SPRUCE_TRAPDOOR.defaultBlockState().setValue(TrapDoorBlock.HALF,Half.TOP).setValue(TrapDoorBlock.OPEN,false).setValue(TrapDoorBlock.POWERED,false).setValue(TrapDoorBlock.WATERLOGGED,false);
  assertTrue(ProjectedBubbleColumnGuard.barrier(trap,EmptyBlockGetter.INSTANCE,BlockPos.ZERO));
  assertTrue(ProjectedBubbleColumnGuard.barrier(Blocks.GLASS_PANE.defaultBlockState(),EmptyBlockGetter.INSTANCE,BlockPos.ZERO));
  assertFalse(ProjectedBubbleColumnGuard.barrier(trap.setValue(TrapDoorBlock.OPEN,true),EmptyBlockGetter.INSTANCE,BlockPos.ZERO));
  assertFalse(ProjectedBubbleColumnGuard.barrier(trap.setValue(TrapDoorBlock.WATERLOGGED,true),EmptyBlockGetter.INSTANCE,BlockPos.ZERO));
  assertFalse(ProjectedBubbleColumnGuard.barrier(Blocks.AIR.defaultBlockState(),EmptyBlockGetter.INSTANCE,BlockPos.ZERO));
 }
 @Test void exclusivePlaceAndStrictBooleanLeaveOtherModesUnchanged(){
  assertTrue(ProjectedBubblePolicy.exclusive(true,false,false,false));assertFalse(ProjectedBubblePolicy.exclusive(false));assertFalse(ProjectedBubblePolicy.exclusive(true,false,true));
  assertFalse(ProjectedBubbleColumnGuard.requested(JsonParser.parseString("{}").getAsJsonObject()));
  assertTrue(ProjectedBubbleColumnGuard.requested(JsonParser.parseString("{\"projected_bubble_column\":true}").getAsJsonObject()));
  assertThrows(IllegalArgumentException.class,()->ProjectedBubbleColumnGuard.requested(JsonParser.parseString("{\"projected_bubble_column\":\"true\"}").getAsJsonObject()));
 }
 @Test void realBucketActionStillUsesOneNormalInputAndTypedPacketAcknowledgement()throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/BucketWaterAction.class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var packet=n.methods.stream().filter(m->m.name.equals("serverBlock")).findFirst().orElseThrow();assertTrue(java.util.stream.StreamSupport.stream(packet.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.owner.endsWith("ProjectedBubbleColumnGuard")&&c.name.equals("expectedPacket")));
  var use=n.methods.stream().filter(m->m.name.equals("useOnce")).findFirst().orElseThrow();assertEquals(1,java.util.stream.StreamSupport.stream(use.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode c&&c.name.equals("useItem")).count());assertFalse(java.util.stream.StreamSupport.stream(use.instructions.spliterator(),false).anyMatch(i->i instanceof MethodInsnNode c&&c.name.equals("setBlock")));
 }
}
