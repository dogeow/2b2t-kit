package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class DryPavingServerConfirmationTest {
    private static final BlockPos CELL = new BlockPos(760995,63,797829);
    private static final String AIR = "Block{minecraft:air}";
    private static final String GRASS = "Block{minecraft:grass_block}[snowy=false]";
    private static final String BRICKS = "Block{minecraft:stone_bricks}";

    @Test void predictedAirAndEarlyOrWrongPacketCannotConfirmOneMine() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","request-a","dry_paving_mine",CELL,AIR);
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,AIR,true));
        confirmation.sent("world-a","request-a","dry_paving_mine",CELL);
        assertFalse(confirmation.confirmed("world-a","request-a","dry_paving_mine",CELL));
        assertFalse(confirmation.serverBlock("world-b","request-a","dry_paving_mine",CELL,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL.above(),AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,AIR,false));
        assertFalse(confirmation.serverUpdateSeen("world-a","request-a","dry_paving_mine",CELL));
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,GRASS,true));
        assertTrue(confirmation.serverUpdateSeen("world-a","request-a","dry_paving_mine",CELL));
        assertEquals(GRASS,confirmation.serverObservedState("world-a","request-a","dry_paving_mine",CELL));
        assertFalse(confirmation.confirmed("world-a","request-a","dry_paving_mine",CELL));
    }

    @Test void laterCorrectionInvalidatesAirAndSpentCellCannotBeRearmed() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","request-a","dry_paving_mine",CELL,AIR);
        confirmation.sent("world-a","request-a","dry_paving_mine",CELL);
        assertTrue(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,AIR,true));
        assertTrue(confirmation.confirmed("world-a","request-a","dry_paving_mine",CELL));
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,GRASS,true));
        assertFalse(confirmation.confirmed("world-a","request-a","dry_paving_mine",CELL));
        confirmation.close("request-a");
        assertThrows(IllegalStateException.class,()->confirmation.begin(
            "world-a","request-retry","dry_paving_mine",CELL,AIR));
        confirmation.begin("world-a","request-place","dry_paving_place",CELL,BRICKS);
        confirmation.sent("world-a","request-place","dry_paving_place",CELL);
        assertFalse(confirmation.serverBlock("world-a","request-a","dry_paving_mine",CELL,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-place","dry_paving_place",CELL,AIR,true));
        assertTrue(confirmation.serverBlock("world-a","request-place","dry_paving_place",CELL,BRICKS,true));
        assertTrue(confirmation.confirmed("world-a","request-place","dry_paving_place",CELL));
        confirmation.close("request-place");
        assertThrows(IllegalStateException.class,()->confirmation.begin(
            "world-a","request-alternate","dry_paving_place",CELL,"Block{minecraft:polished_andesite}"));
    }

    @Test void bridgeEmitsScopedDryPavingReceipt() throws Exception {
        ClassNode node = new ClassNode();
        try(var stream=getClass().getResourceAsStream(
                "/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(stream);
            new ClassReader(stream).accept(node,0);
        }
        var finish=node.methods.stream().filter(method->method.name.equals("finish")).findFirst().orElseThrow();
        List<String> constants=new ArrayList<>(),calls=new ArrayList<>();
        for(var instruction:finish.instructions) {
            if(instruction instanceof LdcInsnNode ldc && ldc.cst instanceof String value)constants.add(value);
            if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        }
        assertTrue(constants.contains("dry_paving_stage"));
        assertTrue(constants.contains("dry_paving_pos"));
        assertTrue(constants.contains("server_confirmed"));
        assertTrue(constants.contains("server_update_seen"));
        assertTrue(constants.contains("confirmation_scope"));
        assertTrue(calls.contains("confirmed"));
        assertTrue(calls.contains("serverObservedState"));
    }

    @Test void bridgeRecordsPredictedAirAfterMiningCallAndNeverFreezesOnEarlyResync() throws Exception {
        ClassNode node = new ClassNode();
        try(var stream=getClass().getResourceAsStream(
                "/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(stream);
            new ClassReader(stream).accept(node,0);
        }
        var input=node.methods.stream().filter(method->method.name.equals("beforeInput"))
            .findFirst().orElseThrow();
        List<AbstractInsnNode> instructions=new ArrayList<>();
        for(var instruction:input.instructions)instructions.add(instruction);
        int start=methodIndex(instructions,"startDestroyBlock",0);
        int continuation=methodIndex(instructions,"continueDestroyBlock",start+1);
        int airCheck=methodIndex(instructions,"isEmptyBlock",continuation+1);
        int localAirRecord=fieldStoreIndex(instructions,"dryPavingClientAirTick",airCheck+1);
        assertTrue(start>=0 && continuation>start && airCheck>continuation
            && localAirRecord>airCheck,
            "local predicted air must be recorded immediately after the mining call");
        var packet=node.methods.stream().filter(method->method.name.equals("serverBlock"))
            .findFirst().orElseThrow();
        for(var instruction:packet.instructions)
            assertFalse(instruction instanceof FieldInsnNode field
                && field.getOpcode()==Opcodes.PUTSTATIC
                && field.name.equals("dryPavingClientAirTick"),
                "a pre-air non-air server update must not stop a legitimate first dig");
        var scope=node.methods.stream().filter(method->method.name.equals("dryPavingRequestGuard"))
            .findFirst().orElseThrow();
        assertTrue(methodIndex(scope.instructions,"scopeValid")>=0,
            "direct guarded requests need the exact world, revision and expiry lease");
    }

    private static int methodIndex(List<AbstractInsnNode> instructions,String method,int from) {
        for(int i=from;i<instructions.size();i++)
            if(instructions.get(i) instanceof MethodInsnNode call && call.name.equals(method))return i;
        return -1;
    }

    private static int methodIndex(org.objectweb.asm.tree.InsnList instructions,String method) {
        List<AbstractInsnNode> list=new ArrayList<>();
        for(var instruction:instructions)list.add(instruction);
        return methodIndex(list,method,0);
    }

    private static int fieldStoreIndex(List<AbstractInsnNode> instructions,String field,int from) {
        for(int i=from;i<instructions.size();i++)
            if(instructions.get(i) instanceof FieldInsnNode access
                    && access.getOpcode()==Opcodes.PUTSTATIC && access.name.equals(field))return i;
        return -1;
    }
}
