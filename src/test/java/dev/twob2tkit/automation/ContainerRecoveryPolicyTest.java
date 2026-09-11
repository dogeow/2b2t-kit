package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ContainerRecoveryPolicyTest {
    @Test void ordinaryMiningCannotBreakEvenAShulker(){
        assertFalse(ContainerRecoveryPolicy.allowed("minecraft:shulker_box",false,3));
    }
    @Test void explicitRetrievalRequiresInventorySpace(){
        assertTrue(ContainerRecoveryPolicy.allowed("minecraft:shulker_box",true,1));
        assertTrue(ContainerRecoveryPolicy.allowed("minecraft:light_blue_shulker_box",true,1));
        assertFalse(ContainerRecoveryPolicy.allowed("minecraft:shulker_box",true,0));
    }
    @Test void otherContainersAndLookalikeIdsRemainProtected(){
        for(String id:new String[]{"minecraft:chest","minecraft:barrel","minecraft:furnace","minecraft:ender_chest","other:shulker_box","minecraft:fake_shulker_box"})
            assertFalse(ContainerRecoveryPolicy.allowed(id,true,3));
    }
}
