package dev.twob2tkit.automation;

/** Additional ordinary block menus adopted only by the current owned opening interaction. */
final class OwnedAddedContainerMenus {
    private OwnedAddedContainerMenus() {}
    static boolean allowed(String menu, boolean currentMaterialOwner, boolean manualInput) {
        return currentMaterialOwner && !manualInput
            && ("HopperMenu".equals(menu) || "DispenserMenu".equals(menu));
    }
}
