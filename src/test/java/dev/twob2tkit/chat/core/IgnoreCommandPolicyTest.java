package dev.twob2tkit.chat.core;

import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

final class IgnoreCommandPolicyTest {
    @Test void recognizesExactStockEmptyListsInEnglishAndChinese() {
        assertEquals(Set.of(), IgnoreCommandPolicy.parseIgnoredList("You are not ignoring anyone.").orElseThrow());
        assertEquals(Set.of(), IgnoreCommandPolicy.parseIgnoredList("你没有屏蔽任何人。").orElseThrow());
        assertEquals(Set.of(), IgnoreCommandPolicy.parseIgnoredList("§6You are not ignoring anyone.§r").orElseThrow());
    }

    @Test void recognizesSpaceSeparatedAccountNamesAndNormalizesCase() {
        assertEquals(Set.of("alice", "b_ob2", "a"), IgnoreCommandPolicy.parseIgnoredList("Ignored: Alice B_ob2 A").orElseThrow());
        assertEquals(Set.of("alice", "bob"), IgnoreCommandPolicy.parseIgnoredList("已屏蔽的玩家：ALICE Bob").orElseThrow());
        assertEquals(Set.of("alice"), IgnoreCommandPolicy.parseIgnoredList("Ignored: ALICE alice").orElseThrow());
        assertEquals(Set.of("alice", "bob"), IgnoreCommandPolicy.parseIgnoredList("§6Ignored:§r Alice §ABob§r").orElseThrow());
    }

    @Test void rejectsChatPrefixesAndQuotedOrEmbeddedReplies() {
        for (String text : new String[]{
                "<player> You are not ignoring anyone.", "<player> Ignored: Alice", "[VIP] Ignored: Alice",
                "player: 你没有屏蔽任何人。", "[服务器] 已屏蔽的玩家：Alice", "\"You are not ignoring anyone.\"",
                "Notice: You are not ignoring anyone.", "You are not ignoring anyone. extra",
                "Ignored: Alice\nYou are not ignoring anyone.", "\nYou are not ignoring anyone."
        }) assertTrue(IgnoreCommandPolicy.parseIgnoredList(text).isEmpty(), text);
    }

    @Test void rejectsUnknownLocaleMessagesAndMalformedLists() {
        for (String text : new String[]{
                "You are ignoring nobody.", "你没有忽略任何人。", "Ignored:", "Ignored: ", "已屏蔽的玩家：",
                "Ignored: Alice, Bob", "Ignored: Alice  Bob", "Ignored: Alice\tBob", "Ignored: Alice ",
                "Ignored: -Bob", "Ignored: 玩家", "Ignored: abcdefghijklmnopq", "Ignored: Alice /op Bob",
                "Ignored: §zAlice", "Ignored: null\u0000", "[Ignored: Alice]"
        }) assertTrue(IgnoreCommandPolicy.parseIgnoredList(text).isEmpty(), text);
        assertTrue(IgnoreCommandPolicy.parseIgnoredList(null).isEmpty());
        assertTrue(IgnoreCommandPolicy.parseIgnoredList("Ignored: " + "A ".repeat(17000)).isEmpty());
    }

    @Test void doesNotToggleAnyoneAlreadyIgnoredRegardlessOfCase() {
        Set<String> ignored = IgnoreCommandPolicy.parseIgnoredList("Ignored: AlIce Bob").orElseThrow();
        assertTrue(IgnoreCommandPolicy.alreadyIgnored(ignored, "ALICE"));
        assertTrue(IgnoreCommandPolicy.commandForUnignoredPlayer("aLiCe", ignored).isEmpty());
        assertTrue(IgnoreCommandPolicy.commandForUnignoredPlayer("BOB", Set.of("Bob")).isEmpty());
        assertEquals("essentials:ignore Charlie",
                IgnoreCommandPolicy.commandForUnignoredPlayer("Charlie", ignored).orElseThrow());
    }

    @Test void willNotConstructCommandsForUnknownStateOrUnsafeNames() {
        assertTrue(IgnoreCommandPolicy.commandForUnignoredPlayer("Alice", null).isEmpty());
        assertTrue(IgnoreCommandPolicy.commandForUnignoredPlayer("Alice", Set.of("Bad Name")).isEmpty());
        for (String name : new String[]{"", " Alice", "Alice ", "Alice\n/op Bob", "@a", "abcdefghijklmnopq", "玩家", "Bob;op"}) {
            assertFalse(IgnoreCommandPolicy.isValidPlayerName(name), name);
            assertTrue(IgnoreCommandPolicy.commandForUnignoredPlayer(name, Set.of()).isEmpty(), name);
        }
        assertFalse(IgnoreCommandPolicy.isValidPlayerName(null));
        assertTrue(IgnoreCommandPolicy.isValidPlayerName("abcdefghijklmnop"));
        assertEquals("essentials:ignore A_1", IgnoreCommandPolicy.commandForUnignoredPlayer("A_1", Set.of()).orElseThrow());
    }
}
