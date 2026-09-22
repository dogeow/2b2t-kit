package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class PrinterInteractionWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){new ClassReader(in).accept(c,0);}return c.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var n:m.instructions)if(n instanceof MethodInsnNode i)r.add(i.name);return r;}
    @Test void interactionIsCheckedBeforeStorageClickAndSneakIsSentAtTheActualClick()throws Exception{
        var c=calls(method("mixin/MultiPlayerGameModeMixin","kit$rememberStorageClick"));assertTrue(c.indexOf("prepareInteraction")<c.indexOf("noteStorageClick"));assertTrue(c.contains("setReturnValue"));
        var p=calls(method("automation/ProfessionalPrinter","prepareInteraction"));assertTrue(p.contains("isPhysicallyDown"));assertTrue(p.contains("send"));
    }
    @Test void ownedContainerIsRecoveredBeforeTheScreenCanDisableCombat()throws Exception{
        var c=calls(method("KitClient","tickNavigation"));assertTrue(c.indexOf("recoverOwnedContainer")<c.indexOf("beforeGuard"));
        var p=calls(method("automation/ProfessionalPrinter","recoverOwnedContainer"));assertTrue(p.indexOf("getCarried")<p.indexOf("closeContainer"));
    }
    @Test void pveScopeCannotEscalateIntoGeneralKillAuraOnMobDamage()throws Exception{
        var c=calls(method("combat/MeteorCombatAssist","arm"));assertTrue(c.indexOf("pveOnly")<c.indexOf("enable"));assertTrue(c.contains("enablePveAura"));assertTrue(c.indexOf("enablePveAura")<c.indexOf("enable"));
    }
}
