package dev.twob2tkit;

import com.google.gson.Gson;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UiDraftTest {
    @Test void unfinishedInputSurvivesSerializationWithoutChangingTheAppliedValue() {
        var draft = new UiDraft(); assertEquals("64", draft.read("Y", "64"));
        draft.remember("Y", "-", "64");
        var copy = new Gson().fromJson(new Gson().toJson(draft), UiDraft.class);
        assertEquals("-", copy.read("Y", "64")); assertEquals("64", copy.baseline.get("Y"));
    }
    @Test void externalChangeInvalidatesOnlyThatFieldNotOtherUnfinishedDrafts() {
        var draft = new UiDraft(); draft.read("X", "10"); draft.read("Z", "20");
        draft.remember("X", "11", "10"); draft.remember("Z", "2-", "20");
        draft.remember("X", "11", "30");
        assertEquals("30", draft.read("X", "30")); assertEquals("2-", draft.read("Z", "20"));
    }
    @Test void successfulCommitAdvancesBaselineAndNormalizesOnlyThatField() {
        var draft = new UiDraft(); draft.read("radius", "32"); draft.remember("radius", "016", "32");
        draft.committed("radius", "16"); assertEquals("16", draft.read("radius", "16"));
        draft.remember("radius", "", "16"); assertEquals("", draft.read("radius", "16"));
    }
    @Test void nullOrMissingLegacyDraftMapsDoNotCrashAForm() {
        var draft = new Gson().fromJson("{\"values\":null,\"baseline\":null}", UiDraft.class);
        assertEquals("", draft.read("name", null)); draft.values.put("name", null);
        assertEquals("fallback", draft.read("name", "fallback"));
        draft.remember("name", null, "fallback"); assertEquals("", draft.read("name", "fallback"));
    }
    @Test void coordinateAndIntegerValidationAcceptsBoundaries() {
        assertEquals(-30_000_000, UiDraft.number("-30000000", "X", -30_000_000, 30_000_000, false));
        assertEquals(99718.13, UiDraft.number("99718.13", "Z", -30_000_000, 30_000_000, false));
        assertEquals(16, UiDraft.number(" 16 ", "半径", 16, 4096, true));
    }
    @Test void nanInfinityPartialValuesAndFractionalCountsCannotAuthorizeApply() {
        for (String raw : new String[]{"NaN", "Infinity", "-Infinity", "", "-", "abc", "1e999", "4097", "15"})
            assertThrows(IllegalArgumentException.class, () -> UiDraft.number(raw, "半径", 16, 4096, true), raw);
        assertThrows(IllegalArgumentException.class, () -> UiDraft.number("16.5", "数量", 1, 9999, true));
    }
    @Test void queryScrollAndSelectionStayIndependentOfSettings() {
        var draft = new UiDraft(); draft.query = "新家"; draft.scroll = 144; draft.remember("selected", "place-7", "");
        var copy = new Gson().fromJson(new Gson().toJson(draft), UiDraft.class);
        assertEquals("新家", copy.query); assertEquals(144, copy.scroll); assertEquals("place-7", copy.read("selected", ""));
    }
    @Test void recordDraftKeepsItsOriginalDatabaseBaselineUntilSaveReallySucceeds() {
        var draft = new UiDraft(); String savedName = "旧地点";
        draft.read("名称", savedName); draft.remember("名称", "新地点", savedName);
        // A temporary model may now contain 新地点 while an overwrite dialog is open.
        // Cancel/close keeps the original database baseline; reopening must retain the uncommitted name.
        var reopened = new Gson().fromJson(new Gson().toJson(draft), UiDraft.class);
        assertEquals("新地点", reopened.read("名称", savedName));
        assertEquals("旧地点", reopened.baseline.get("名称"));
    }
}
