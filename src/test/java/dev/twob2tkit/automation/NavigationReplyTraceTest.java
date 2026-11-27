package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class NavigationReplyTraceTest {
    private JsonObject finished() {
        var nav = new JsonObject(); nav.addProperty("outcome", "arrived"); nav.addProperty("injury_interrupted", false);
        var trace = new JsonArray(); for (int i = 0; i < 500; i++) trace.add(i); nav.add("trace", trace); return nav;
    }

    @Test void theNavigationsOwnReplyKeepsTheFullTrace() {
        var nav = finished();
        var reply = AutomationBridge.navigationForReply(nav, "materials-nav-1", "materials-nav-1");
        assertEquals(500, reply.getAsJsonArray("trace").size());
    }

    @Test void laterRepliesKeepTheSummaryButNotTheTrace() {
        var nav = finished();
        var reply = AutomationBridge.navigationForReply(nav, "materials-nav-1", "materials-scan-2");
        assertFalse(reply.has("trace"));
        assertEquals("materials-nav-1", reply.get("trace_request").getAsString());
        assertEquals("arrived", reply.get("outcome").getAsString());
        assertFalse(reply.get("injury_interrupted").getAsBoolean(), "readers still see the injury flag");
        assertEquals(500, nav.getAsJsonArray("trace").size(), "the retained terminal snapshot itself is not modified");
    }
}
