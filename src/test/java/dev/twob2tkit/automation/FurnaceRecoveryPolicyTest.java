package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class FurnaceRecoveryPolicyTest {
    private boolean permit(String id, boolean[] v, int space) {
        return FurnaceRecoveryPolicy.allowed(id,v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],v[8],v[9],v[10],space);
    }
    private boolean[] valid() { return new boolean[]{true,true,true,true,true,true,true,false,false,false,true}; }
    @Test void onlyExplicitOwnedServerEmptyOrdinaryFurnaceWithPickupRoomIsAllowed() {
        assertTrue(permit("minecraft:furnace", valid(), 1));
        for (String id : new String[]{"minecraft:chest","minecraft:barrel","minecraft:blast_furnace","minecraft:smoker","minecraft:shulker_box","other:furnace"})
            assertFalse(permit(id,valid(),2));
        assertFalse(permit("minecraft:furnace",valid(),0));
    }
    @Test void everyMissingProofOrUnsafeConditionRejects() {
        for (int i = 0; i < 11; i++) {
            boolean[] v = valid(); v[i] = !v[i];
            assertFalse(permit("minecraft:furnace",v,3), "Changed required condition " + i);
        }
    }
    @Test void normalMiningAndShulkerRecoveryNeverGainTheFurnaceException() {
        assertFalse(ContainerRecoveryPolicy.allowed("minecraft:furnace",false,3));
        assertFalse(ContainerRecoveryPolicy.allowed("minecraft:furnace",true,3));
    }
    @Test void observationsUseActualCurrentConnectionServerPacketsAndNativeMiningConfirmation() throws Exception {
        Path source=Path.of("src/client/java/dev/twob2tkit");
        var session=Files.readString(source.resolve("automation/EmptyFurnaceRecovery.java"));
        assertTrue(session.contains("sender == connection"));assertTrue(session.contains("menu != c.player.containerMenu"));
        assertTrue(session.contains("current == menu"));assertTrue(session.contains("items.size() < 3"));
        assertTrue(session.contains("expected_content_serial"));assertTrue(session.contains("counts[slot] = item.getCount()"));
        assertTrue(session.contains("c.player.closeContainer()"));assertTrue(session.contains("Blocks.HOPPER"));
        var mixin=Files.readString(source.resolve("mixin/BucketInventoryUpdatesMixin.java"));
        assertTrue(mixin.contains("serverFurnaceSlot(this, packet.getContainerId()"));
        assertTrue(mixin.contains("serverFurnaceContent(this, packet.containerId(), packet.items())"));
        var bridge=Files.readString(source.resolve("automation/AutomationBridge.java"));
        assertTrue(bridge.contains("EmptyFurnaceRecovery.opening(c,currentMaterialRequest(c,r)"));
        assertTrue(bridge.contains("EmptyFurnaceRecovery.prepare(c,r,pos,currentMaterialRequest(c,r)"));
        assertTrue(bridge.contains("EmptyFurnaceRecovery.validateMining(c,active,target)"));
        assertTrue(bridge.contains("ordinaryMiningConfirmation.begin(c,session(c),str(r,\"id\"),pos,underwater)"));
    }
}
