package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class EndermanExpiredBudgetWiringTest {
    @Test void currentAngryEndermanDefenseRunsBeforeTheGenericExpiredBudgetHold() throws Exception {
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerRangedCombat.class")) {
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var method=node.methods.stream().filter(m->m.name.equals("tick")).findFirst().orElseThrow();
        int index=0,defend=-1,genericHold=-1,creeperEscape=-1,safetyRise=-1;
        for(var instruction:method.instructions) {
            if(instruction instanceof MethodInsnNode call) {
                if(call.name.equals("defendEnderman")&&defend<0)defend=index;
                if(call.name.equals("holdForMissingObservation")&&genericHold<0)genericHold=index;
                if(call.name.equals("evadeCreeper")&&creeperEscape<0)creeperEscape=index;
                if(call.name.equals("safetyRise")&&safetyRise<0)safetyRise=index;
            }
            index++;
        }
        assertTrue(creeperEscape>=0&&creeperEscape<defend,"Urgent creeper evasion keeps priority");
        assertTrue(safetyRise>defend,"A generic rise cannot repeatedly preempt legal enderman sword defense");
        assertTrue(defend>=0&&genericHold>defend,"Expired attack budget cannot bypass the enderman look-down/sword branch");
        var defense=node.methods.stream().filter(m->m.name.equals("defendEnderman")).findFirst().orElseThrow();
        boolean swordAttack=false,bowSelection=false,lookDown=false;
        for(var instruction:defense.instructions) {
            if(instruction instanceof MethodInsnNode call) {
                swordAttack|=call.name.equals("attack");bowSelection|=call.name.equals("selectBow");
            }
            if(instruction instanceof LdcInsnNode constant&&Float.valueOf(90).equals(constant.cst))lookDown=true;
        }
        assertTrue(swordAttack);assertFalse(bowSelection);assertTrue(lookDown);
    }
}
