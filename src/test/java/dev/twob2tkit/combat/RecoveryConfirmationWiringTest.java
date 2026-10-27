package dev.twob2tkit.combat;

import java.util.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class RecoveryConfirmationWiringTest {
    @Test void disconnectedClientHasAFreshNonemptyScopeBeforeFirstWorldJoin()throws Exception {
        var init=code("automation/AutomationBridge").methods.stream().filter(m->m.name.equals("<clinit>")).findFirst().orElseThrow();
        var instructions=init.instructions.toArray();
        for(int i=0;i<instructions.length;i++)if(instructions[i] instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC&&f.name.equals("worldSession")){
            assertTrue(instructions[i-1] instanceof MethodInsnNode call&&call.name.equals("toString"));
            assertTrue(instructions[i-2] instanceof MethodInsnNode call&&call.owner.equals("java/util/UUID")&&call.name.equals("randomUUID"));return;
        }
        fail("Fresh title scope must be initialized");
    }
    @Test void explicitRecoveryDispatchDoesNotEnterIdleHandoffThatRejectsHealthLocks()throws Exception {
        var method=code("automation/AutomationBridge").methods.stream().filter(m->m.name.equals("dispatch")).findFirst().orElseThrow();
        var seen=new HashSet<String>();
        for(var instruction:method.instructions){
            if(instruction instanceof LdcInsnNode value&&value.cst instanceof String s)seen.add(s);
            if(instruction instanceof MethodInsnNode call&&call.name.equals("preemptIdleForPlayer")){
                assertTrue(seen.containsAll(Set.of("connect_server","client_quit","confirm_recovery")));return;
            }
        }
        fail("Expected ordinary dispatch preemption boundary");
    }
    ClassNode code(String name)throws Exception{var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){assertNotNull(in);new ClassReader(in).accept(c,0);}return c;}
    List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode c)r.add(c.name);return r;}
    @Test void realDispatchValidatesBeforeAcknowledgingAndArmsDefenseBeforeClosingPause()throws Exception{
        var cls=code("automation/AutomationBridge");var method=cls.methods.stream().filter(m->m.name.equals("confirmExplicitRecovery")).findFirst().orElseThrow();var c=calls(method);
        assertTrue(c.indexOf("require")<c.indexOf("acknowledgeExplicitChat"));assertTrue(c.indexOf("acknowledgeExplicitChat")<c.indexOf("armPveGuard"));
        assertTrue(c.indexOf("armPveGuard")<c.indexOf("setScreen"));assertTrue(c.containsAll(List.of("recoveryIncident","guardArmed","pveOnly","save")));
        assertTrue(c.indexOf("hasItem")<c.indexOf("require"));
        var dispatcher=cls.methods.stream().filter(m->calls(m).contains("confirmExplicitRecovery")).findFirst().orElseThrow();var d=calls(dispatcher);assertTrue(d.indexOf("guard")<d.indexOf("confirmExplicitRecovery"));
        assertTrue(dev.twob2tkit.automation.InterfacePausePolicy.readOrStop("confirm_recovery"));
    }
    @Test void chatAcknowledgementNeverMasqueradesAsTheUiButton()throws Exception{
        var e=code("combat/EmergencyExit");var chat=e.methods.stream().filter(m->m.name.equals("acknowledgeExplicitChat")).findFirst().orElseThrow();
        assertTrue(calls(chat).contains("clearByExplicitChat"));assertFalse(calls(chat).contains("clearByUser"));
        var original=e.methods.stream().filter(m->m.name.equals("acknowledge")).findFirst().orElseThrow();assertTrue(calls(original).contains("clearByUser"));
    }
}
