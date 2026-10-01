package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TerrainServerConfirmationTest {
    private static final BlockPos SURFACE = new BlockPos(760994,63,797865);
    private static final BlockPos FOUNDATION = SURFACE.below();
    private static final String AIR = "Block{minecraft:air}";
    private static final String GRASS = "Block{minecraft:grass_block}[snowy=false]";

    @Test void everyStageHasAnExactServerTargetAndExpectedState() {
        assertEquals(SURFACE,TerrainServerConfirmation.target("lift_grass",FOUNDATION));
        assertEquals(FOUNDATION,TerrainServerConfirmation.target("mine_stone",FOUNDATION));
        assertEquals(FOUNDATION,TerrainServerConfirmation.target("place_dirt",FOUNDATION));
        assertEquals(SURFACE,TerrainServerConfirmation.target("restore_grass",FOUNDATION));
        assertEquals(AIR,TerrainServerConfirmation.expectedState("lift_grass",GRASS));
        assertEquals(AIR,TerrainServerConfirmation.expectedState("mine_stone",GRASS));
        assertEquals("Block{minecraft:dirt}",TerrainServerConfirmation.expectedState("place_dirt",GRASS));
        assertEquals(GRASS,TerrainServerConfirmation.expectedState("restore_grass",GRASS));
        assertThrows(IllegalArgumentException.class,()->TerrainServerConfirmation.target("other",FOUNDATION));
    }

    @Test void droppedPacketNeverBecomesSuccess() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","request-a","lift_grass",SURFACE,AIR);
        confirmation.sent("world-a","request-a","lift_grass",SURFACE);
        assertFalse(confirmation.confirmed("world-a","request-a","lift_grass",SURFACE));
        confirmation.close("request-a");
        assertFalse(confirmation.confirmed("world-a","request-a","lift_grass",SURFACE));
        assertThrows(IllegalStateException.class,()->confirmation.begin(
            "world-a","request-retry","lift_grass",SURFACE,AIR));
    }

    @Test void earlyLateWrongSessionAndOldRequestPacketCannotAcknowledge() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","request-a","lift_grass",SURFACE,AIR);
        assertFalse(confirmation.serverBlock("world-a","request-a","lift_grass",SURFACE,AIR,true));
        confirmation.sent("world-a","request-a","lift_grass",SURFACE);
        assertFalse(confirmation.serverBlock("world-b","request-a","lift_grass",SURFACE,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","old-request","lift_grass",SURFACE,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-a","mine_stone",SURFACE,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-a","lift_grass",FOUNDATION,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","request-a","lift_grass",SURFACE,AIR,false));
        assertFalse(confirmation.serverBlock("world-a","request-a","lift_grass",SURFACE,GRASS,true));
        assertFalse(confirmation.confirmed("world-a","request-a","lift_grass",SURFACE));
        assertTrue(confirmation.serverBlock("world-a","request-a","lift_grass",SURFACE,AIR,true));
        assertTrue(confirmation.confirmed("world-a","request-a","lift_grass",SURFACE));
        confirmation.close("request-a");
        assertFalse(confirmation.serverBlock("world-a","request-a","lift_grass",SURFACE,AIR,true));
    }

    @Test void identicalOldStageCannotBeRearmedAtTheSamePosition() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","old","mine_stone",FOUNDATION,AIR);
        confirmation.sent("world-a","old","mine_stone",FOUNDATION);
        confirmation.close("old");
        assertThrows(IllegalStateException.class,()->confirmation.begin(
            "world-a","new","mine_stone",FOUNDATION,AIR));
        confirmation.begin("world-a","place","place_dirt",FOUNDATION,"Block{minecraft:dirt}");
        confirmation.sent("world-a","place","place_dirt",FOUNDATION);
        assertFalse(confirmation.serverBlock("world-a","old","mine_stone",FOUNDATION,AIR,true));
        assertFalse(confirmation.serverBlock("world-a","place","place_dirt",FOUNDATION,AIR,true));
        assertFalse(confirmation.confirmed("world-a","place","place_dirt",FOUNDATION));
        assertTrue(confirmation.serverBlock("world-a","place","place_dirt",FOUNDATION,
            "Block{minecraft:dirt}",true));
        assertEquals("matched_server_block_update_after_native_send",confirmation.scope());
    }

    @Test void oldWorldSessionCannotAcknowledgeNewWorldSession() {
        var confirmation = new TerrainServerConfirmation();
        confirmation.begin("world-a","old","restore_grass",SURFACE,GRASS);
        confirmation.sent("world-a","old","restore_grass",SURFACE);
        confirmation.begin("world-b","new","restore_grass",SURFACE,GRASS);
        confirmation.sent("world-b","new","restore_grass",SURFACE);
        assertFalse(confirmation.serverBlock("world-a","old","restore_grass",SURFACE,GRASS,true));
        assertFalse(confirmation.serverBlock("world-b","old","restore_grass",SURFACE,GRASS,true));
        assertTrue(confirmation.serverBlock("world-b","new","restore_grass",SURFACE,GRASS,true));
    }

    @Test void bridgeOnlyEmitsServerConfirmedReceiptAfterStageConfirmation() throws Exception {
        ClassNode node = new ClassNode();
        try(var stream=getClass().getResourceAsStream(
                "/dev/twob2tkit/automation/AutomationBridge.class")) {
            assertNotNull(stream);
            new ClassReader(stream).accept(node,0);
        }
        var finish=node.methods.stream().filter(m->m.name.equals("finish")).findFirst().orElseThrow();
        List<String> constants=new ArrayList<>(),calls=new ArrayList<>();
        for(var instruction:finish.instructions) {
            if(instruction instanceof LdcInsnNode ldc && ldc.cst instanceof String value)constants.add(value);
            if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        }
        assertTrue(constants.contains("server_confirmed"));
        assertTrue(constants.contains("confirmation_scope"));
        assertTrue(calls.contains("confirmed"));
        assertTrue(calls.contains("close"));
    }
}
