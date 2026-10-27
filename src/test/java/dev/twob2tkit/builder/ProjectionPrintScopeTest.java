package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionPrintScopeTest {
    @Test void excludedLevelsDoNotEnterTheCurrentWorkPlane() {
        var original=new ArrayList<>(List.of(56,68,68,72));
        assertEquals(List.of(68,68),ProjectionPrintScope.select(original,y->y==68));
        assertEquals(List.of(56,68,68,72),original);
    }
    @Test void emptyAndFullScopesStayExplicit() {
        assertEquals(List.of(),ProjectionPrintScope.select(List.of(56,72),y->false));
        assertEquals(List.of(56,72),ProjectionPrintScope.select(List.of(56,72),y->true));
    }
    private MethodNode method(String name)throws Exception {
        var cls=new ClassNode();try(var input=getClass().getResourceAsStream("/dev/twob2tkit/builder/ProjectionBuildJob.class")){new ClassReader(input).accept(cls,0);}
        return cls.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    @Test void liveWorkScopeControlsContinuousPrintAndAnEmptyScopeCannotEnableIt()throws Exception {
        var load=method("load");var names=new ArrayList<String>();
        for(var i:load.instructions)if(i instanceof MethodInsnNode call)names.add(call.name);
        assertTrue(names.containsAll(List.of("currentPositions","isEmpty","getFirst","allMatch")));
        assertTrue(names.indexOf("currentPositions")<names.indexOf("allMatch"));
        assertTrue(load.instructions.iterator().hasNext());
    }
    @Test void scopedMaterialDemandDoesNotReplaceFullModelMatching()throws Exception {
        var recount=method("recount");int matchedWrite=-1,scope=-1,merge=-1,index=0;
        for(var i:recount.instructions){
            if(i instanceof FieldInsnNode field&&field.name.equals("matched")&&i.getOpcode()==181)matchedWrite=index;
            if(i instanceof MethodInsnNode call&&call.name.equals("projectionBatchAllows"))scope=index;
            if(i instanceof MethodInsnNode call&&call.name.equals("merge"))merge=index;
            index++;
        }
        assertTrue(matchedWrite>=0&&scope>matchedWrite&&merge>scope);
    }
}
