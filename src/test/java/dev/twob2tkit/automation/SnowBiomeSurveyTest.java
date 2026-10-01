package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SnowBiomeSurveyTest {
    @Test void coarseGridIsBoundedUniqueAndDeterministic() {
        var grid = SnowBiomeSurvey.grid(-32, 80, 64, 32);
        assertEquals(25, grid.size());
        assertEquals(grid.size(), grid.stream().distinct().count());
        assertEquals(new SnowBiomeSurvey.SamplePoint(-96, 16), grid.getFirst());
        assertEquals(new SnowBiomeSurvey.SamplePoint(32, 144), grid.getLast());
        assertTrue(grid.stream().allMatch(point -> Math.abs(point.x() + 32) <= 64
                && Math.abs(point.z() - 80) <= 64));
    }

    @Test void invalidOrUnboundedGridsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SnowBiomeSurvey.grid(0, 0, 15, 32));
        assertThrows(IllegalArgumentException.class,
                () -> SnowBiomeSurvey.grid(0, 0, 97, 32));
        assertThrows(IllegalArgumentException.class,
                () -> SnowBiomeSurvey.grid(0, 0, 64, 8));
    }

    @Test void scanRequiresLiveServerChunkEvidenceBeforeReadingBiome() throws Exception {
        List<MethodInsnNode> calls = calls(method("SnowBiomeSurvey", "scan"));
        int chunkSource = index(calls, "getChunkSource");
        int getChunk = index(calls, "getChunk");
        int serverChunk = index(calls, "isServerChunk");
        int height = index(calls, "getHeight");
        int biome = index(calls, "getBiome");
        assertTrue(chunkSource >= 0 && chunkSource < getChunk
            && getChunk < serverChunk && serverChunk < height && height < biome);
        assertTrue(calls.get(serverChunk).owner.endsWith(
                "/runtime/engine/LoadedServerChunkEvidence"));
        assertFalse(calls.stream().anyMatch(call -> call.name.equals("hasChunkAt")
            || call.name.equals("hasChunk")));
        assertTrue(calls.stream().anyMatch(call -> call.name.equals("coldEnoughToSnow")));
        assertTrue(calls.stream().anyMatch(call -> call.name.equals("getPrecipitationAt")));
    }

    @Test void detailedBlockScanRejectsCachedOnlyChunksBeforeReadingBlocks() throws Exception {
        List<MethodInsnNode> calls = calls(method("AutomationBridge", "scanCell"));
        int getChunk = index(calls, "getChunk");
        int serverChunk = index(calls, "isServerChunk");
        int blockRead = index(calls, "getBlockState");
        assertTrue(getChunk >= 0 && getChunk < serverChunk && serverChunk < blockRead);
        assertTrue(calls.get(serverChunk).owner.endsWith(
                "/runtime/engine/LoadedServerChunkEvidence"));
        assertFalse(calls.stream().anyMatch(call -> call.name.equals("hasChunkAt")));
    }

    @Test void bridgeExposesOnlyTheReadOnlySurveyAndAdvertisesItsProtocol() throws Exception {
        assertTrue(calls(method("AutomationBridge", "dispatch")).stream()
                .anyMatch(call -> call.owner.endsWith("/SnowBiomeSurvey")
                        && call.name.equals("scan")));
        boolean protocol = false;
        for (var instruction : method("AutomationBridge", "snapshot").instructions) {
            if (instruction instanceof LdcInsnNode value
                    && "snow_biome_survey_protocol".equals(value.cst)) {
                protocol = true;
                break;
            }
        }
        assertTrue(protocol);
    }

    private MethodNode method(String owner, String name) throws Exception {
        var node = new ClassNode();
        try (var input = getClass().getResourceAsStream(
                "/dev/twob2tkit/automation/" + owner + ".class")) {
            assertNotNull(input);
            new ClassReader(input).accept(node, 0);
        }
        return node.methods.stream().filter(method -> method.name.equals(name))
                .findFirst().orElseThrow();
    }

    private List<MethodInsnNode> calls(MethodNode method) {
        var calls = new ArrayList<MethodInsnNode>();
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call) calls.add(call);
        }
        return calls;
    }

    private int index(List<MethodInsnNode> calls, String name) {
        for (int index = 0; index < calls.size(); index++) {
            if (calls.get(index).name.equals(name)) return index;
        }
        return -1;
    }
}
