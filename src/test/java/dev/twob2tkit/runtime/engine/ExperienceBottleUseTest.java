package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExperienceBottleUseTest {
    @Test
    void requiresFreshOwnershipAndStopsOnAProtectionOrInputChange() {
        var request = JsonParser.parseString("""
            {"player_uuid":"player","world_session":"world","lease_id":"lease","task_session":"job",
             "control_revision":7,"input_serial":2,"issued_at":9900,"expires_at":12000}
            """).getAsJsonObject();
        var state = JsonParser.parseString("""
            {"world_session":"world","control_revision":7,"phase":"done","time":9975,
             "connected":true,"guard_armed":true,"guard_pve_only":true,"auto_log":true,
             "game_interaction":{"interaction_serial":2}}
            """).getAsJsonObject();
        state.addProperty("runtime_version", EngineBuildVersion.VALUE);
        var lease = JsonParser.parseString("""
            {"id":"lease","world_session":"world","job_session":"job","kind":"materials","revision":7}
            """).getAsJsonObject();

        assertTrue(ExperienceBottleUse.owned(request, state, lease, 10000, "player"));
        assertFalse(ExperienceBottleUse.owned(request, state, lease, 13000, "player"));
        assertFalse(ExperienceBottleUse.owned(request, state, lease, 10000, "other"));
        for (String key : new String[] {"guard_busy", "manual_movement", "flight", "native_material_busy"}) {
            state.addProperty(key, true);
            assertFalse(ExperienceBottleUse.owned(request, state, lease, 10000, "player"), key);
            state.remove(key);
        }
        state.getAsJsonObject("game_interaction").addProperty("interaction_serial", 3);
        assertFalse(ExperienceBottleUse.owned(request, state, lease, 10000, "player"));
        state.getAsJsonObject("game_interaction").addProperty("interaction_serial", 2);
        lease.addProperty("revision", 8);
        assertFalse(ExperienceBottleUse.owned(request, state, lease, 10000, "player"));
    }
}
