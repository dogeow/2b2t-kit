package dev.twob2tkit;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Gson 字段名与 twob2tkit.json 中 storageSnapshots 结构一致即可持久化。 */
final class KitConfigStorageTest {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	@Test
	void storageSnapshotJsonShapeRoundTrips() {
		ConfigShape config = new ConfigShape();
		SnapshotShape snapshot = new SnapshotShape();
		snapshot.dimension = "minecraft:overworld";
		snapshot.x = 382848;
		snapshot.y = 44;
		snapshot.z = 311338;
		snapshot.title = "资源箱";
		snapshot.note = "小麦 种子";
		snapshot.colorId = "red";
		snapshot.lastSeenEpochMillis = 1_700_000_000_000L;
		snapshot.items.add(new ItemShape("minecraft:wheat_seeds", "小麦种子", 64));
		config.storageSnapshots.add(snapshot);

		String json = GSON.toJson(config);
		assertTrue(json.contains("\"storageSnapshots\""));
		assertTrue(json.contains("minecraft:wheat_seeds"));

		ConfigShape loaded = GSON.fromJson(json, ConfigShape.class);
		assertEquals(1, loaded.storageSnapshots.size());
		SnapshotShape roundTrip = loaded.storageSnapshots.getFirst();
		assertEquals("minecraft:overworld", roundTrip.dimension);
		assertEquals(382848, roundTrip.x);
		assertEquals(1, roundTrip.items.size());
		assertEquals("minecraft:wheat_seeds", roundTrip.items.getFirst().id);
		assertEquals(64, roundTrip.items.getFirst().count);
	}

	static final class ConfigShape {
		List<SnapshotShape> storageSnapshots = new ArrayList<>();
	}

	static final class SnapshotShape {
		String dimension = "";
		int x;
		int y;
		int z;
		String title = "箱子";
		String blockId = "";
		String colorId = "";
		String note = "";
		long lastSeenEpochMillis;
		List<ItemShape> items = new ArrayList<>();
	}

	static final class ItemShape {
		String id = "";
		String name = "";
		int count;

		ItemShape() {
		}

		ItemShape(String id, String name, int count) {
			this.id = id;
			this.name = name;
			this.count = count;
		}
	}
}
