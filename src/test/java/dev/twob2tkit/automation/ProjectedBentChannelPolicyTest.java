package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
final class ProjectedBentChannelPolicyTest {
    static List<Integer> goal(){return List.of(0,1,2,3,4,5,6,7);}
    @Test void exactWestThenSouthEightCellPathHasNoDuplicate(){
        var seen=new HashSet<String>();
        for(int i=0;i<8;i++)assertTrue(seen.add(ProjectedBentChannelPolicy.dx(i)+","+ProjectedBentChannelPolicy.dz(i)));
        assertEquals(-3,ProjectedBentChannelPolicy.dx(7));assertEquals(4,ProjectedBentChannelPolicy.dz(7));
    }
    @Test void dryOnlyBeforeUseAndTransientFlowAllowedOnlyAfterSource(){
        assertTrue(ProjectedBentChannelPolicy.levels(goal(),Collections.nCopies(8,-1),true));
        assertFalse(ProjectedBentChannelPolicy.levels(goal(),goal(),true));
        assertTrue(ProjectedBentChannelPolicy.levels(goal(),List.of(0,1,-1,-1,-1,-1,-1,-1),false));
        assertTrue(ProjectedBentChannelPolicy.levels(goal(),goal(),false));
        assertFalse(ProjectedBentChannelPolicy.levels(goal(),Collections.nCopies(8,-1),false));
    }
    @Test void wrongShapeSolidLavaAndWrongModelAreRejected(){
        assertFalse(ProjectedBentChannelPolicy.levels(goal(),List.of(0,1,2,3,4,5,6,-2),false));
        assertFalse(ProjectedBentChannelPolicy.levels(goal(),List.of(0,1,2,3,4,5,6,16),false));
        assertFalse(ProjectedBentChannelPolicy.levels(List.of(0,1,2,3,4,5,6,6),goal(),false));
        assertFalse(ProjectedBentChannelPolicy.levels(goal(),List.of(0),false));
    }
    @Test void modeCannotBeUsedForFillingOrCombinedWithOtherModes(){
        assertTrue(ProjectedBentChannelPolicy.exclusive(true,false,false,false,false,false));
        assertFalse(ProjectedBentChannelPolicy.exclusive(false,false,false,false,false,false));
        for(int i=0;i<5;i++){boolean[] v=new boolean[5];v[i]=true;assertFalse(ProjectedBentChannelPolicy.exclusive(true,v[0],v[1],v[2],v[3],v[4]));}
    }
    @Test void realGuardRevalidatesCompletedChamberAndOriginalFlowModel() throws Exception {
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedBentChannelGuard.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var require=node.methods.stream().filter(v->v.name.equals("require")).findFirst().orElseThrow();
        var calls=java.util.stream.StreamSupport.stream(require.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        for(String name:List.of("requireCompleted","levels","getBlockState","getBlockEntity","getEntities","inVisibleLayer","loaded"))assertTrue(calls.contains(name),name);
    }
}
