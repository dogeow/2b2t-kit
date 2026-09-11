package dev.twob2tkit.skills;
import dev.twob2tkit.UiFeature;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class SkillMenuWiringTest {
    private ClassNode type(String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n;}
    @Test void productionAndGlobalSearchExposeTheSkillMenu(){assertEquals(UiFeature.Category.PRODUCTION,UiFeature.SKILLS.category);assertTrue(UiFeature.SKILLS.matches("技能"));assertTrue(UiFeature.SKILLS.matches("Voyager"));}
    @Test void skillBrowsingDoesNotExecuteSkillsOrWriteInput()throws Exception{
        for(var m:type("KitSkillPages").methods)for(var n:m.instructions)if(n instanceof MethodInsnNode call)
            assertFalse(Set.of("start","toggle","run","send","setDown","useItemOn","attack").contains(call.name),m.name+" calls "+call.name);
    }
    @Test void genericListRefreshIsOptionalAndKeepsSearchSelectionAndScroll()throws Exception{
        var n=type("KitCollectionScreen");assertTrue(n.methods.stream().anyMatch(m->m.name.equals("refreshWhen")));assertTrue(n.methods.stream().anyMatch(m->m.name.equals("tick")));
        var p=type("KitCollectionScreen$Items").methods.stream().filter(m->m.name.equals("populate")).findFirst().orElseThrow();var calls=new HashSet<String>();
        for(var i:p.instructions)if(i instanceof MethodInsnNode c)calls.add(c.name);assertTrue(calls.containsAll(Set.of("scrollAmount","setScrollAmount","setSelected")));
    }
}
