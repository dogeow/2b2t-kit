package dev.twob2tkit.mixin;

import net.minecraft.world.inventory.AbstractContainerMenu;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Observe the existing drag state; never change it or manufacture a second click. */
@Mixin(AbstractContainerMenu.class)
public interface InventoryMenuDiagnosticsAccess {
    @Accessor("quickcraftStatus") int kit$getQuickcraftStatus();
}
