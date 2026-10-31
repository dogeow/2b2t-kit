package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import com.google.gson.JsonParser;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
final class CompletedSourceSupplyTest {
    @Test void onlySelectedMiddleMayBeTransientAndEveryOtherCellMustBeSource(){
        var levels=new ArrayList<>(Collections.nCopies(27,0));assertTrue(SourceColumnSupplyPolicy.completedChamber(levels,-1));
        levels.set(25,-1);assertTrue(SourceColumnSupplyPolicy.completedChamber(levels,25));assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,-1));
        levels.set(25,8);assertTrue(SourceColumnSupplyPolicy.completedChamber(levels,25));levels.set(0,8);assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,25));
    }
    @Test void outerSeedsAndBadShapesCannotBeExcluded(){
        var levels=new ArrayList<>(Collections.nCopies(27,0));for(int i:new int[]{0,2,24,26,-2,27})assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,i));
        assertFalse(SourceColumnSupplyPolicy.completedChamber(Collections.nCopies(26,0),1));levels.set(1,-2);assertFalse(SourceColumnSupplyPolicy.completedChamber(levels,1));
    }
    @Test void completedTopMustBeTheExactOriginalGradient(){
        assertTrue(SourceColumnSupplyPolicy.completedTop(List.of(2,1,0),List.of(2,1,0)));
        for(var actual:List.of(List.of(-1,-1,-1),List.of(0,0,0),List.of(2,8,0)))assertFalse(SourceColumnSupplyPolicy.completedTop(List.of(2,1,0),actual));
        assertFalse(SourceColumnSupplyPolicy.completedTop(List.of(0,1,2),List.of(0,1,2)));
    }
    @Test void completedFlagIsExplicitAndStrictBoolean(){
        var request=new com.google.gson.JsonObject();assertFalse(ProjectedSourceColumnSupplyGuard.completedOverflowRequested(request));
        request.addProperty("source_supply_completed_overflow",true);assertTrue(ProjectedSourceColumnSupplyGuard.completedOverflowRequested(request));
        for(var value:java.util.List.of(new com.google.gson.JsonPrimitive("true"),new com.google.gson.JsonPrimitive(1),com.google.gson.JsonNull.INSTANCE,new com.google.gson.JsonArray())){
            var bad=new com.google.gson.JsonObject();bad.add("source_supply_completed_overflow",value);
            assertThrows(IllegalArgumentException.class,()->ProjectedSourceColumnSupplyGuard.completedOverflowRequested(bad));
        }
    }
    @Test void workspaceStillRunsExistingShieldAndFullColumnProof()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedSourceColumnSupplyGuard.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var workspace=node.methods.stream().filter(v->v.name.equals("requireWorkspace")).findFirst().orElseThrow();var calls=java.util.stream.StreamSupport.stream(workspace.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        assertTrue(calls.contains("require"),"old dry-top proof retained");assertTrue(calls.contains("requireCompletedSupply"));assertTrue(calls.contains("completedTop"));
        var shield=node.methods.stream().filter(v->v.name.equals("shieldedWorkspace")).findFirst().orElseThrow();var checks=java.util.stream.StreamSupport.stream(shield.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();assertTrue(checks.contains("requireWorkspace"));assertTrue(checks.contains("shieldedActor"));
    }
}
