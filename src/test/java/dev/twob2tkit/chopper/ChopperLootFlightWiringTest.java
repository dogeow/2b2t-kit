package dev.twob2tkit.chopper;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperLootFlightWiringTest {
    private List<String> calls(String owner,String method)throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/chopper/"+owner+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var target=node.methods.stream().filter(m->m.name.equals(method)).findFirst().orElseThrow();
        var calls=new ArrayList<String>();
        for(var instruction:target.instructions)if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        return calls;
    }
    @Test void actualLootMovementUsesManagedPlannerInsteadOfDirectWalking()throws Exception{
        var tick=calls("ChopperLoot","tick");assertTrue(tick.contains("tick"));assertFalse(tick.contains("walkToward"));
        assertTrue(calls("ChopperLootFlight","plan").contains("search"));
        assertTrue(calls("ChopperLootFlight","tick").containsAll(List.of("safeBody","replan","speed")));
    }
    @Test void movementPauseCannotResetLeafMiningProgress()throws Exception{
        var pause=calls("ChopperLootFlight","pause");assertTrue(pause.contains("releaseWalk"));
        assertFalse(pause.contains("releaseMine"));assertFalse(pause.contains("holdStill"));
    }
    @Test void disappearanceRequiresInventoryObservation()throws Exception{
        var picked=calls("ChopperLoot","notePicked");assertTrue(picked.containsAll(List.of("inventoryCount","verifiedPickupGain")));
    }
    @Test void stopAndCombatPauseCloseOnlyTheOwnedFlightLease()throws Exception{
        assertTrue(calls("AutoChopper","stop").contains("closeFlight"));
        assertTrue(calls("AutoChopper","tick").contains("closeFlight"));
        var close=calls("ChopperLootFlight","close");assertTrue(close.containsAll(List.of("closeKeepingFlight","close")));
    }
}
