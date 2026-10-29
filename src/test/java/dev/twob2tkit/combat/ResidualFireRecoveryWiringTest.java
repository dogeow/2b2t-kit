package dev.twob2tkit.combat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ResidualFireRecoveryWiringTest {
    @Test void onlyLingeringMobFireInCurrentLoadedSafeBodyMayWait()throws Exception{
        var s=Files.readString(Path.of("src/client/java/dev/twob2tkit/combat/ResidualFireRecovery.java"));
        assertTrue(s.contains("source.is(DamageTypes.ON_FIRE)"));
        assertTrue(s.contains("source.getEntity() instanceof Enemy"));
        assertTrue(s.contains("LoadedServerChunkEvidence.isServerChunk"));
        assertTrue(s.contains("p.isInLava()"));assertTrue(s.contains("CampfireBlock.LIT"));
        assertTrue(s.contains("Projectile projectile"));assertTrue(s.contains("p.hasLineOfSight(e)"));
        assertFalse(s.contains("setHealth("));assertFalse(s.contains("clearByUser"));assertFalse(s.contains("SafetyHoldStore"));
    }
    @Test void waitingKeepsGuardAndOriginalRequestsButYieldsCombatAndWorkInputs()throws Exception{
        var s=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        int start=s.indexOf("if(enabled&&dev.twob2tkit.combat.ResidualFireRecovery.active())");
        int end=s.indexOf("if(active!=null&&op.equals(\"navigate\")",start);
        var pause=s.substring(start,end);
        assertTrue(pause.contains("suspendStandaloneCombatForAirReturn(c)"));
        assertTrue(pause.contains("guardBusy=true"));assertTrue(pause.contains("deadline++"));
        assertTrue(pause.contains("materialAirNavigation.pause(c)"));
        assertFalse(pause.contains("guardScope=null"));assertFalse(pause.contains("active=null"));
        var e=Files.readString(Path.of("src/client/java/dev/twob2tkit/combat/EmergencyExit.java"));
        assertTrue(e.contains("c.player.getHealth()<14"));
        assertTrue(e.contains("environmentalDamage.observe("));
        assertTrue(e.contains("原地反复受到环境伤害，停止工作并锁定自动重连"));
    }
}
