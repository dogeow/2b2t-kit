package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/** Read-only evidence for carried hive items; never infers live block occupancy. */
final class BeehiveItemObservation {
    private BeehiveItemObservation() {}

    static void add(JsonObject target, ItemStack stack) {
        if (stack.isEmpty() || !(stack.is(Items.BEEHIVE) || stack.is(Items.BEE_NEST))) return;
        var bees = stack.get(DataComponents.BEES);
        target.addProperty("bee_component_present", bees != null);
        if (bees != null) target.addProperty("bee_count", bees.bees().size());
    }
}
