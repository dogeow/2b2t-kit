package dev.twob2tkit.runtime.engine;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.chunk.LevelChunk;

/**
 * Evidence that a client chunk is the live server-supplied chunk.
 *
 * <p>Bobby inserts {@code FakeChunk} instances from its disk cache into the
 * normal client chunk cache.  Presence in that cache is therefore not enough
 * for automation that is about to trust blocks or biomes.  Bobby is optional,
 * so the check resolves its type without a compile-time dependency and fails
 * closed whenever an installed Bobby cannot be identified.</p>
 */
public final class LoadedServerChunkEvidence {
    private static final String BOBBY_MOD_ID = "bobby";
    private static final String BOBBY_PACKAGE = "de.johni0702.minecraft.bobby.";
    private static final String BOBBY_FAKE_CHUNK = BOBBY_PACKAGE + "FakeChunk";

    private LoadedServerChunkEvidence() {}

    /** Check a chunk obtained with {@code ChunkStatus.FULL, false}. */
    public static boolean isServerChunk(Level expectedLevel, LevelChunk chunk) {
        if (expectedLevel == null || chunk == null || chunk.getLevel() != expectedLevel) return false;
        return isServerChunkClass(chunk.getClass(), BobbyRuntime.loaded, BobbyRuntime.fakeChunk);
    }

    /** Use Bobby's already-resolved type when its native adapter is connected. */
    static boolean isServerChunk(Level expectedLevel, LevelChunk chunk, Class<?> bobbyFakeChunk) {
        if (expectedLevel == null || chunk == null || chunk.getLevel() != expectedLevel) return false;
        return isServerChunkClass(chunk.getClass(), true, bobbyFakeChunk);
    }

    static boolean isServerChunkClass(Class<?> actual, boolean bobbyLoaded, Class<?> bobbyFakeChunk) {
        if (actual == null || isBobbyOwnedChunk(actual)) return false;
        if (!bobbyLoaded) return true;
        // An installed but incompatible Bobby must never turn an unknown cached
        // chunk into authorization for a block or biome read.
        return bobbyFakeChunk != null && !bobbyFakeChunk.isAssignableFrom(actual);
    }

    static boolean isBobbyOwnedChunk(Class<?> type) {
        for (Class<?> current = type; current != null; current = current.getSuperclass()) {
            if (current.getName().startsWith(BOBBY_PACKAGE)) return true;
        }
        return false;
    }

    private static final class BobbyRuntime {
        private static final boolean loaded = bobbyLoaded();
        private static final Class<?> fakeChunk = loaded ? loadFakeChunk() : null;

        private static boolean bobbyLoaded() {
            try {
                return FabricLoader.getInstance().isModLoaded(BOBBY_MOD_ID);
            } catch (LinkageError | RuntimeException incompatibleLoader) {
                // Loader uncertainty is handled like an installed, unresolved
                // Bobby so callers fail closed.
                return true;
            }
        }

        private static Class<?> loadFakeChunk() {
            try {
                return Class.forName(BOBBY_FAKE_CHUNK, false,
                    LoadedServerChunkEvidence.class.getClassLoader());
            } catch (ClassNotFoundException | LinkageError | RuntimeException incompatibleBobby) {
                return null;
            }
        }
    }
}
