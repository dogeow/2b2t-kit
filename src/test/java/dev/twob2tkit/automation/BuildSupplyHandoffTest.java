package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BuildSupplyHandoffTest {
    private record Menu(int id) {}
    private static final BuildSupplyTask.IdleMenuHandoff RELEASED=BuildSupplyTask.IdleMenuHandoff.RELEASED;
    private static final BuildSupplyTask.IdleMenuHandoff CLOSE=BuildSupplyTask.IdleMenuHandoff.CLOSE_OWNED;
    private static final BuildSupplyTask.IdleMenuHandoff WAITING=BuildSupplyTask.IdleMenuHandoff.WAITING;

    @Test void taskWithoutAnOpenKeepsOriginalInventoryAndLaterPlayerMenus() {
        var original=new Menu(0);var playerMenu=new Menu(5);
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,null,original,false,true));
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,null,playerMenu,false,true));
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,original,original,false,true));
    }
    @Test void onlyExactAcknowledgedMenuCanBeClosedEvenWhenServerIdIsReused() {
        var original=new Menu(0);var opened=new Menu(5);var replacement=new Menu(5);
        assertEquals(opened,replacement);assertNotSame(opened,replacement);
        assertEquals(CLOSE,BuildSupplyTask.idleMenuHandoff(original,opened,opened,false,true));
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,opened,replacement,false,true));
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,opened,original,false,true));
    }
    @Test void unresolvedOpenNeverClaimsReleasedOrAdoptsAnotherMenu() {
        var original=new Menu(0);var unacknowledged=new Menu(5);
        assertEquals(WAITING,BuildSupplyTask.idleMenuHandoff(original,null,original,true,true));
        assertEquals(WAITING,BuildSupplyTask.idleMenuHandoff(original,null,unacknowledged,true,true));
    }
    @Test void cursorItemsRemainUntouchedAndPreventReleaseAcrossMenuOwnership() {
        var original=new Menu(0);var opened=new Menu(5);var replacement=new Menu(6);
        for(var current:List.of(original,opened,replacement))
            assertEquals(WAITING,BuildSupplyTask.idleMenuHandoff(original,opened,current,false,false));
        assertEquals(WAITING,BuildSupplyTask.idleMenuHandoff(original,opened,null,false,true));
    }
    @Test void releaseRequiresClosePostconditionRatherThanOnlySendingClose() {
        var original=new Menu(0);var opened=new Menu(5);
        assertEquals(CLOSE,BuildSupplyTask.idleMenuHandoff(original,opened,opened,false,true));
        // A close operation which leaves the same menu active is still unresolved.
        assertNotEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,opened,opened,false,true));
        assertEquals(RELEASED,BuildSupplyTask.idleMenuHandoff(original,opened,original,false,true));
    }
    @Test void hostHandoffStopsInputsBeforeDecisionAndRechecksWithoutCursorClicks()throws Exception {
        var node=code();var handoff=method(node,"closeForIdleHandoff");var calls=calls(handoff);
        assertEquals("close",calls.getFirst());
        assertEquals(2,Collections.frequency(calls,"idleMenuHandoff"));
        assertEquals(1,Collections.frequency(calls,"closeContainer"));
        assertTrue(calls.indexOf("closeContainer")>calls.indexOf("idleMenuHandoff"));
        assertFalse(calls.contains("acknowledgeOpenedMenu"));
        assertFalse(calls.contains("handleContainerInput"));assertFalse(calls.contains("setCarried"));
        var close=node.methods.stream().filter(m->m.name.equals("close")&&m.desc.contains(";Z")).findFirst().orElseThrow();
        assertTrue(fields(close).containsAll(Set.of("openedMenu","containerMenu","level")));
        assertTrue(java.util.stream.StreamSupport.stream(close.instructions.spliterator(),false)
            .anyMatch(i->i.getOpcode()==Opcodes.IF_ACMPNE));
        assertTrue(fields(method(node,"acknowledgeOpenedMenu")).containsAll(Set.of("closed","openingPending","originalMenu","openedMenu")));
        assertTrue(calls(method(node,"ownsMenu")).contains("acknowledgeOpenedMenu"));
    }
    private static ClassNode code()throws Exception {
        var result=new ClassNode();try(var in=BuildSupplyHandoffTest.class.getResourceAsStream("/dev/twob2tkit/automation/BuildSupplyTask.class")) {
            assertNotNull(in);new ClassReader(in).accept(result,0);
        }return result;
    }
    private static MethodNode method(ClassNode node,String name) {
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private static List<String> calls(MethodNode method) {
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode c)result.add(c.name);return result;
    }
    private static Set<String> fields(MethodNode method) {
        var result=new HashSet<String>();for(var i:method.instructions)if(i instanceof FieldInsnNode f)result.add(f.name);return result;
    }
}
