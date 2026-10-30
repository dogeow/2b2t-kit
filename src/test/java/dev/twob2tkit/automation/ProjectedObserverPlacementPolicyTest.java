package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
final class ProjectedObserverPlacementPolicyTest {
    @Test void horizontalObserverFacingUsesTheActual26_2LookingDirection(){
        assertEquals(new ProjectedObserverPlacementPolicy.Angles(0,0),ProjectedObserverPlacementPolicy.look("south"));
        assertEquals(new ProjectedObserverPlacementPolicy.Angles(180,0),ProjectedObserverPlacementPolicy.look("north"));
        assertEquals(new ProjectedObserverPlacementPolicy.Angles(90,0),ProjectedObserverPlacementPolicy.look("west"));
        assertEquals(new ProjectedObserverPlacementPolicy.Angles(-90,0),ProjectedObserverPlacementPolicy.look("east"));
    }
    @Test void verticalFacingAndInvalidInput(){
        assertEquals(-90,ProjectedObserverPlacementPolicy.look("up").pitch());assertEquals(90,ProjectedObserverPlacementPolicy.look("down").pitch());
        assertThrows(IllegalArgumentException.class,()->ProjectedObserverPlacementPolicy.look("diagonal"));
    }
    @Test void realGuardRequiresLoadedModelAirVisibleSupportAndVanillaPrediction()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedObserverPlacementGuard.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var m=node.methods.stream().filter(v->v.name.equals("require")).findFirst().orElseThrow();
        var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        for(String name:new String[]{"isServerChunk","inVisibleLayer","isAir","getBlockEntity","getStateForPlacement","getClickedPos","getEntities"})assertTrue(calls.contains(name),name);
        assertFalse(calls.contains("setBlock"));assertFalse(calls.contains("acknowledge"));
    }
    @Test void existingInteractionRechecksTheSameVisibleRayBeforeNormalUse()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        long uses=node.methods.stream().flatMap(m->java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false)).filter(i->i instanceof MethodInsnNode c&&c.owner.equals("dev/twob2tkit/automation/ProjectedObserverPlacementGuard")&&c.name.equals("require")).count();assertEquals(2,uses);
    }
}
