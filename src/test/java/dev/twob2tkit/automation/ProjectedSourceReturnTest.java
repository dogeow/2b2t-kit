package dev.twob2tkit.automation;
import com.google.gson.JsonParser;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.Items;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.material.Fluids;
import org.junit.jupiter.api.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedSourceReturnTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 private static ClassNode node(String name)throws Exception{
  var n=new ClassNode();try(var in=ProjectedSourceReturnTest.class.getResourceAsStream("/"+name+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n;
 }
 private static List<MethodInsnNode> calls(ClassNode n,String method){return java.util.stream.StreamSupport.stream(n.methods.stream().filter(m->m.name.equals(method)).findFirst().orElseThrow().instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->(MethodInsnNode)i).toList();}
 @Test void onlyAnExactMiddleSourceOfAValidatedProfileMayReceiveWater(){
  var lo=new BlockPos(10,59,20);assertTrue(ProjectedSourceReturnGuard.centre(lo,lo.above(8).east(2),lo.above(8).east(),9));assertTrue(ProjectedSourceReturnGuard.centre(lo,lo.above(3).east(2),lo.above().east(),4));
  assertFalse(ProjectedSourceReturnGuard.centre(lo,lo.above(8).east(2),lo.above(8),9));assertFalse(ProjectedSourceReturnGuard.centre(lo,lo.above(8).east(2),lo.above(9).east(),9));assertFalse(ProjectedSourceReturnGuard.centre(lo,lo.above(7).east(2),lo.east(),9));
 }
 @Test void returnFlagAndExclusivePlaceDoNotRelaxOtherBucketOperations(){
  assertFalse(ProjectedSourceReturnGuard.requested(JsonParser.parseString("{}").getAsJsonObject()));assertTrue(ProjectedSourceReturnGuard.requested(JsonParser.parseString("{\"projected_source_return\":true}").getAsJsonObject()));assertThrows(IllegalArgumentException.class,()->ProjectedSourceReturnGuard.requested(JsonParser.parseString("{\"projected_source_return\":1}").getAsJsonObject()));
  assertTrue(ProjectedBubblePolicy.exclusive(true,false,false,false));assertFalse(ProjectedBubblePolicy.exclusive(false));assertFalse(ProjectedBubblePolicy.exclusive(true,true));
 }
 @Test void actualVanillaEmptyBucketBlockUseIsInertAndExistingWaterCanBeReplaced(){
  assertSame(InteractionResult.PASS,Items.BUCKET.useOn(null));assertTrue(Blocks.WATER.defaultBlockState().canBeReplaced(Fluids.WATER));
 }
 @Test void originalSourceWallsAndCompletedOverflowAreRevalidated()throws Exception{
  var list=calls(node("dev/twob2tkit/automation/ProjectedSourceReturnGuard"),"require").stream().map(c->c.name).toList();
  for(var name:List.of("requireCompleted","schematicWorld","completedTop","getBlockEntity","isCollisionShapeFullBlock"))assertTrue(list.contains(name),name);
  assertFalse(list.contains("setBlock"));assertFalse(list.contains("setItem"));
 }
 @Test void oneWaterUsePrecedesOnlyOneSeparateVerificationProbe()throws Exception{
  var list=calls(node("dev/twob2tkit/automation/BucketWaterAction"),"useOnce");assertEquals(1,list.stream().filter(c->c.name.equals("useItem")).count());assertEquals(1,list.stream().filter(c->c.owner.endsWith("ProjectedSourceReturnGuard")&&c.name.equals("probe")).count());
  int use=-1,probe=-1;for(int i=0;i<list.size();i++){if(list.get(i).name.equals("useItem"))use=i;if(list.get(i).name.equals("probe"))probe=i;}assertTrue(use>=0&&probe>use);
 }
 @Test void verificationUsesTheRealInertVisibleFaceWithoutBucketFallbackOrSyntheticPackets()throws Exception{
  var list=calls(node("dev/twob2tkit/automation/ProjectedSourceReturnGuard"),"probe");assertEquals(1,list.stream().filter(c->c.name.equals("useItemOn")).count());assertFalse(list.stream().anyMatch(c->c.name.equals("useItem")||c.name.equals("setBlock")||c.name.equals("acknowledge")||c.name.equals("send")));assertTrue(list.stream().anyMatch(c->c.name.equals("clip")));assertTrue(list.stream().anyMatch(c->c.name.equals("require")));
 }
 @Test void vanillaBlockInteractionReallyRepliesWithSupportAndAdjacentBlockUpdates()throws Exception{
  var list=calls(node("net/minecraft/server/network/ServerGamePacketListenerImpl"),"handleUseItemOn");assertEquals(2,list.stream().filter(c->c.owner.equals("net/minecraft/network/protocol/game/ClientboundBlockUpdatePacket")&&c.name.equals("<init>")).count());
 }
 @Test void ordinaryFillNeverGetsTheReturnShieldException(){
  var r=JsonParser.parseString("{\"op\":\"bucket_fill\",\"projected_source_return\":true}").getAsJsonObject();assertFalse(ProjectedSourceReturnGuard.shieldedWorkspace(null,r));
 }
}
