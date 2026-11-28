package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.component.Bees;
import net.minecraft.world.item.component.TypedEntityData;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BeehiveBlockEntity;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import com.google.gson.JsonParser;
import com.google.gson.JsonObject;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

/** Offline vanilla component evidence; this does not exercise server or printer. */
class BeehiveComponentRoundTripTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion();
        net.minecraft.server.Bootstrap.bootStrap();
        var lookup = net.minecraft.data.registries.VanillaRegistries.createLookup();
        net.minecraft.core.registries.BuiltInRegistries.DATA_COMPONENT_INITIALIZERS.build(lookup)
            .forEach(net.minecraft.core.component.DataComponentInitializers.PendingComponents::apply);
    }

    @Test void occupiedHiveComponentsSurviveItemAndReapplication() {
        var original = new BeehiveBlockEntity(BlockPos.ZERO, Blocks.BEEHIVE.defaultBlockState());
        CompoundTag beeTag = new CompoundTag();
        beeTag.putString("CustomName", "test-bee");
        var data = TypedEntityData.<EntityType<?>>of(EntityTypes.BEE, beeTag);
        original.storeBee(new BeehiveBlockEntity.Occupant(data, 42, 2400));
        original.storeBee(new BeehiveBlockEntity.Occupant(data, 89, 1800));
        Bees before = original.collectComponents().get(DataComponents.BEES);
        assertNotNull(before);
        assertEquals(2, before.bees().size());
        for (var item : new net.minecraft.world.item.Item[]{Items.BEEHIVE, Items.BEE_NEST}) {
            var stack = new ItemStack(item);
            stack.applyComponents(original.collectComponents());
            assertEquals(before, stack.get(DataComponents.BEES));
            var restored = new BeehiveBlockEntity(BlockPos.ZERO, Blocks.BEEHIVE.defaultBlockState());
            restored.applyComponentsFromItemStack(stack.copy());
            assertEquals(2, restored.getOccupantCount());
            assertEquals(before, restored.collectComponents().get(DataComponents.BEES));
        }
    }

    @Test void vanillaLootCopiesBeesOnlyWithSilkTouch() throws Exception {
        for (String name : new String[]{"beehive", "bee_nest"}) {
            var path = "data/minecraft/loot_table/blocks/" + name + ".json";
            var stream = getClass().getClassLoader().getResourceAsStream(path);
            assertNotNull(stream, path);
            try (var reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
                var json = JsonParser.parseReader(reader).getAsJsonObject();
                var pool = json.getAsJsonArray("pools").get(0).getAsJsonObject();
                var entry = pool.getAsJsonArray("entries").get(0).getAsJsonObject();
                var silkEntry = name.equals("beehive")
                    ? entry.getAsJsonArray("children").get(0).getAsJsonObject() : entry;
                var conditionOwner = name.equals("beehive") ? silkEntry : pool;
                assertTrue(conditionOwner.getAsJsonArray("conditions").toString().contains("minecraft:silk_touch"), name);
                assertEquals("minecraft:" + name, silkEntry.get("name").getAsString());
                var functions = silkEntry.getAsJsonArray("functions");
                var copy = functions.get(0).getAsJsonObject();
                assertEquals("minecraft:copy_components", copy.get("function").getAsString());
                assertEquals("block_entity", copy.get("source").getAsString());
                assertTrue(copy.getAsJsonArray("include").toString().contains("minecraft:bees"));
                var state = functions.get(1).getAsJsonObject();
                assertEquals("minecraft:copy_state", state.get("function").getAsString());
                assertTrue(state.getAsJsonArray("properties").toString().contains("honey_level"));
            }
        }
    }

    @Test void carriedHiveObservationReportsOnlyExplicitBeeComponents() {
        var empty = new ItemStack(Items.BEEHIVE);
        var emptyObservation = new JsonObject();
        BeehiveItemObservation.add(emptyObservation, empty);
        assertTrue(emptyObservation.get("bee_component_present").getAsBoolean());
        assertEquals(0, emptyObservation.get("bee_count").getAsInt());

        var absent = new ItemStack(Items.BEEHIVE);
        absent.remove(DataComponents.BEES);
        var missing = new JsonObject();
        BeehiveItemObservation.add(missing, absent);
        assertFalse(missing.get("bee_component_present").getAsBoolean());
        assertFalse(missing.has("bee_count"));

        var tag = new CompoundTag();
        tag.putString("CustomName", "private-bee-name");
        var data = TypedEntityData.<EntityType<?>>of(EntityTypes.BEE, tag);
        var occupants = new Bees(java.util.List.of(new BeehiveBlockEntity.Occupant(data, 42, 2400)));
        for (var item : new net.minecraft.world.item.Item[]{Items.BEEHIVE, Items.BEE_NEST}) {
            var stack = new ItemStack(item);
            stack.set(DataComponents.BEES, occupants);
            var observed = new JsonObject();
            BeehiveItemObservation.add(observed, stack);
            assertTrue(observed.get("bee_component_present").getAsBoolean());
            assertEquals(1, observed.get("bee_count").getAsInt());
            assertFalse(observed.toString().contains("private-bee-name"));
        }
        var other = new JsonObject();
        BeehiveItemObservation.add(other, new ItemStack(Items.DIRT));
        assertEquals(0, other.size());
    }
}
