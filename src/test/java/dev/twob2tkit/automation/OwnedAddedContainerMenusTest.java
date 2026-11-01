package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OwnedAddedContainerMenusTest {
    @Test void theRecordedOwnedHopperOpenAndOrdinaryDropperShareSupportedContainerOwnership() {
        assertTrue(OwnedAddedContainerMenus.allowed("HopperMenu",true,false));
        assertTrue(OwnedAddedContainerMenus.allowed("DispenserMenu",true,false));
    }
    @Test void userOpenedOrForeignTaskMenusAreNeverAdopted() {
        for (String menu : new String[]{"HopperMenu","DispenserMenu"}) {
            assertFalse(OwnedAddedContainerMenus.allowed(menu,false,false));
            assertFalse(OwnedAddedContainerMenus.allowed(menu,true,true));
            assertFalse(OwnedAddedContainerMenus.allowed(menu,false,true));
        }
    }
    @Test void inventoryMerchantAndUnknownScreensKeepTheirExistingSeparateRules() {
        for (String menu : new String[]{"InventoryMenu","MerchantMenu","CreativeModeInventoryScreen","OtherMenu","x.HopperMenu","hoppermenu",""})
            assertFalse(OwnedAddedContainerMenus.allowed(menu,true,false),menu);
        assertFalse(OwnedAddedContainerMenus.allowed(null,true,false));
    }
    @Test void theActualHostUsesThePolicyWithCurrentOwnerAndManualInputEvidence() throws Exception {
        var node=new org.objectweb.asm.tree.ClassNode();
        try(var in=getClass().getResourceAsStream("AutomationBridge.class")) {
            assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);
        }
        boolean policy=false,currentOwner=false,manual=false;
        for(var method:node.methods)if(method.name.equals("ownsMaterialMenu"))for(var instruction:method.instructions)
            if(instruction instanceof org.objectweb.asm.tree.MethodInsnNode call) {
                policy|=call.owner.endsWith("OwnedAddedContainerMenus")&&call.name.equals("allowed");
                currentOwner|=call.name.equals("currentMaterialRequest");
                manual|=call.name.equals("manualMovementDown");
            }
        assertTrue(policy&&currentOwner&&manual);
    }
    @Test void actualHostAdvertisesTheNewCapabilityBeforeClientsTryTheNewMenus() throws Exception {
        var node=new org.objectweb.asm.tree.ClassNode();
        try(var in=getClass().getResourceAsStream("AutomationBridge.class")) {
            assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);
        }
        boolean flag=false;
        for(var method:node.methods)if(method.name.equals("snapshot"))for(var instruction:method.instructions)
            if(instruction instanceof org.objectweb.asm.tree.LdcInsnNode constant)
                flag|="owned_added_container_menu_protocol".equals(constant.cst);
        assertTrue(flag);
    }
}
