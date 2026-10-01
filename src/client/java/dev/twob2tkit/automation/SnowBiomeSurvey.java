package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;

import java.util.ArrayList;
import java.util.List;

/**
 * Read-only biome samples from chunks the multiplayer client actually has.
 *
 * <p>This is only a coarse discovery hint.  It never asks the server to locate
 * anything and never treats an unloaded chunk as a negative biome result.</p>
 */
final class SnowBiomeSurvey {
    static final int PROTOCOL = 1;
    private static final int MIN_RADIUS = 16;
    private static final int MAX_RADIUS = 96;
    private static final int MIN_STRIDE = 16;
    private static final int MAX_STRIDE = 128;
    private static final int MAX_SAMPLES = 169;
    private static final double MAX_CENTER_DISTANCE = 8.0;

    private SnowBiomeSurvey() {}

    record SamplePoint(int x, int z) {}

    static List<SamplePoint> grid(int centerX, int centerZ, int radius, int stride) {
        if (radius < MIN_RADIUS || radius > MAX_RADIUS)
            throw new IllegalArgumentException("Snow biome survey radius must be 16..96");
        if (stride < MIN_STRIDE || stride > MAX_STRIDE)
            throw new IllegalArgumentException("Snow biome survey stride must be 16..128");
        long width = (2L * radius) / stride + 1L;
        if (width * width > MAX_SAMPLES)
            throw new IllegalArgumentException("Snow biome survey grid is too large");
        var result = new ArrayList<SamplePoint>();
        for (int x = centerX - radius; x <= centerX + radius; x += stride) {
            for (int z = centerZ - radius; z <= centerZ + radius; z += stride) {
                result.add(new SamplePoint(x, z));
            }
        }
        return List.copyOf(result);
    }

    static JsonObject scan(Minecraft client, JsonObject request) {
        if (client.player == null || client.level == null)
            throw new IllegalStateException("Snow biome survey requires a loaded world");
        JsonArray center = request.getAsJsonArray("center");
        if (center == null || center.size() != 2)
            throw new IllegalArgumentException("Snow biome survey needs an x/z center");
        int centerX = exactInt(center.get(0), "center x");
        int centerZ = exactInt(center.get(1), "center z");
        int radius = request.has("radius") ? exactInt(request.get("radius"), "radius") : 64;
        int stride = request.has("stride") ? exactInt(request.get("stride"), "stride") : 64;
        if (Math.hypot(client.player.getX() - (centerX + .5),
                client.player.getZ() - (centerZ + .5)) > MAX_CENTER_DISTANCE)
            throw new IllegalArgumentException("Snow biome survey center is not the current loaded waypoint");

        List<SamplePoint> grid = grid(centerX, centerZ, radius, stride);
        JsonArray samples = new JsonArray();
        int unloaded = 0;
        for (SamplePoint point : grid) {
            int chunkX = Math.floorDiv(point.x(), 16);
            int chunkZ = Math.floorDiv(point.z(), 16);
            // ClientLevel.hasChunkAt is not an authoritative loaded-chunk test
            // in 26.1.  Query the client chunk cache before every biome read.
            var chunk=client.level.getChunkSource().getChunk(
                    chunkX,chunkZ,ChunkStatus.FULL,false);
            if (!LoadedServerChunkEvidence.isServerChunk(client.level, chunk)) {
                unloaded++;
                continue;
            }
            int surfaceY = client.level.getHeight(Heightmap.Types.MOTION_BLOCKING,
                    point.x(), point.z());
            surfaceY = Math.max(client.level.getMinY(),
                    Math.min(client.level.getMaxY() - 1, surfaceY));
            BlockPos position = new BlockPos(point.x(), surfaceY, point.z());
            var biomeHolder = client.level.getBiome(position);
            var biome = biomeHolder.value();
            JsonObject sample = new JsonObject();
            sample.add("pos", ints(point.x(), surfaceY, point.z()));
            sample.add("chunk", ints(chunkX, chunkZ));
            sample.addProperty("biome", biomeHolder.unwrapKey()
                    .map(key -> key.identifier().toString()).orElse("unknown"));
            sample.addProperty("precipitation", biome
                    .getPrecipitationAt(position, client.level.getSeaLevel()).getSerializedName());
            sample.addProperty("cold_enough_to_snow",
                    biome.coldEnoughToSnow(position, client.level.getSeaLevel()));
            sample.addProperty("base_temperature", biome.getBaseTemperature());
            samples.add(sample);
        }
        JsonObject result = new JsonObject();
        result.add("center", center.deepCopy());
        result.addProperty("radius", radius);
        result.addProperty("stride", stride);
        result.addProperty("requested_samples", grid.size());
        result.addProperty("loaded_samples", samples.size());
        result.addProperty("unloaded_samples", unloaded);
        result.add("samples", samples);
        return result;
    }

    private static JsonArray ints(int... values) {
        JsonArray result = new JsonArray();
        for (int value : values) result.add(value);
        return result;
    }

    private static int exactInt(JsonElement value, String label) {
        if (value == null || !value.isJsonPrimitive()
                || !value.getAsJsonPrimitive().isNumber())
            throw new IllegalArgumentException("Snow biome survey " + label + " must be an integer");
        double number = value.getAsDouble();
        if (!Double.isFinite(number) || number != Math.rint(number)
                || number < Integer.MIN_VALUE || number > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Snow biome survey " + label + " must be an integer");
        return (int) number;
    }
}
