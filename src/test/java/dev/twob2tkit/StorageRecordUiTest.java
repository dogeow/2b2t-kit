package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Handle;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Verify the active unified list, including visible rows rather than tooltip-only counts. */
final class StorageRecordUiTest {
    @Test void actualStorageEntryEnablesQueryAwareVisibleSummaryAndRefreshesLifecycle() throws Exception {
        var method = method("KitRecordPages", "storage");
        assertTrue(calls(method).contains("dev/twob2tkit/storage/StorageLifecycle.refresh"));
        assertTrue(calls(method).contains("dev/twob2tkit/KitCollectionScreen.summary"));
        assertTrue(references(method).contains("dev/twob2tkit/storage/StorageLabels.cacheSummary"));
        assertTrue(references(method).contains("dev/twob2tkit/KitConfig$StorageSnapshot.scopedKey"));
    }

    @Test void collectionRendersSummaryAsTextAndResolvesItWithCurrentQuery() throws Exception {
        var content = method("KitCollectionScreen$Items$Entry", "extractContent");
        assertTrue(calls(content).contains("dev/twob2tkit/KitCollectionScreen.summaryText"));
        assertTrue(calls(content).contains("dev/twob2tkit/KitUi.text"));
        var summary = method("KitCollectionScreen", "summaryText");
        assertTrue(Arrays.stream(summary.instructions.toArray()).anyMatch(i ->
            i instanceof FieldInsnNode f && f.name.equals("query")));
        assertTrue(calls(summary).contains("java/util/function/BiFunction.apply"));
    }

    @Test void storageRecordActionsKeepScopeAndDisableUnavailableTravelOrSupply() throws Exception {
        var calls = new ArrayList<String>();
        for (var method : node("KitRecordPages").methods)
            if (method.name.equals("storage") || method.name.startsWith("lambda$storage$")) calls.addAll(calls(method));
        assertTrue(calls.contains("dev/twob2tkit/storage/StorageLifecycle.usable"));
        assertTrue(calls.contains("dev/twob2tkit/storage/StorageLifecycle.statusLabel"));
        assertTrue(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.scopedKey"));
        assertFalse(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.key"));
    }

    @Test void itemDetailDraftsAlsoUseServerScopedStorageIdentity() throws Exception {
        var calls = new ArrayList<String>();
        for (var method : node("storage/StorageDetailScreen").methods)
            if (method.name.equals("openUnifiedDetail") || method.name.startsWith("lambda$openUnifiedDetail$")) calls.addAll(calls(method));
        assertTrue(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.scopedKey"));
        assertFalse(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.key"));
    }

    @Test void retainedLegacyFallbackCannotGuideToInvalidRecordsOrDeleteOtherServers() throws Exception {
        assertTrue(calls(method("storage/StorageRecordsScreen", "startGuide"))
            .contains("dev/twob2tkit/storage/StorageLifecycle.usable"));
        var calls = new ArrayList<String>();
        for (var method : node("storage/StorageRecordsScreen").methods)
            if (method.name.equals("delete") || method.name.startsWith("lambda$delete$")) calls.addAll(calls(method));
        assertTrue(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.scopedKey"));
        assertFalse(calls.contains("dev/twob2tkit/KitConfig$StorageSnapshot.key"));
    }

    private static ClassNode node(String type) throws Exception {
        var node = new ClassNode();
        try (var stream = StorageRecordUiTest.class.getResourceAsStream("/dev/twob2tkit/" + type + ".class")) {
            assertNotNull(stream);new ClassReader(stream).accept(node, 0);
        }
        return node;
    }
    private static MethodNode method(String type, String name) throws Exception {
        return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static List<String> calls(MethodNode method) {
        var result = new ArrayList<String>();
        for (var i : method.instructions) if (i instanceof MethodInsnNode call) result.add(call.owner + "." + call.name);
        return result;
    }
    private static List<String> references(MethodNode method) {
        var result = new ArrayList<String>();
        for (var i : method.instructions) if (i instanceof InvokeDynamicInsnNode call)
            for (var argument : call.bsmArgs) if (argument instanceof Handle handle) result.add(handle.getOwner() + "." + handle.getName());
        return result;
    }
}
