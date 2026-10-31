package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class SourceRoofAccessTest {
 @Test void onlyTheMiddleOriginalRoofOfTheFourRowChamberCanUseThisAccess(){
  var b=new ProjectedSourceColumnPolicy.Bounds(28,59,86,30,62,86);
  assertTrue(ProjectedSourceColumnGuard.middleRoof(b,new BlockPos(29,64,86)));
  for(var p:new BlockPos[]{new BlockPos(28,64,86),new BlockPos(30,64,86),new BlockPos(29,63,86),new BlockPos(29,64,87)})assertFalse(ProjectedSourceColumnGuard.middleRoof(b,p));
  assertFalse(ProjectedSourceColumnGuard.middleRoof(new ProjectedSourceColumnPolicy.Bounds(28,59,86,30,67,86),new BlockPos(29,69,86)));
 }
 @Test void theAdditionalFlagIsExplicitAndBoolean(){
  var r=new JsonObject();assertFalse(ProjectedSourceColumnGuard.roofRequested(r));r.addProperty("projected_source_roof",true);assertTrue(ProjectedSourceColumnGuard.roofRequested(r));r.addProperty("projected_source_roof","true");assertThrows(IllegalArgumentException.class,()->ProjectedSourceColumnGuard.roofRequested(r));
 }
 @Test void reopeningRevalidatesCompletedChamberModelAndCurrentLoadedCell()throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedSourceColumnGuard.class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var m=n.methods.stream().filter(v->v.name.equals("requireRoofAccess")).findFirst().orElseThrow();var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
  for(var name:new String[]{"requireCompleted","middleRoof","schematicWorld","loaded","inVisibleLayer","getBlockEntity","intersects"})assertTrue(calls.contains(name),name);assertFalse(calls.contains("setBlock"));
 }
}
