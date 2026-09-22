package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionAuditTest {
 @Test void aDoorStateDifferenceIsNotANewDoor(){assertEquals("state_only",ProjectionAudit.kind("minecraft:oak_door","minecraft:oak_door",false));}
 @Test void missingAndOccupiedRequireDifferentWorkflows(){assertEquals("missing",ProjectionAudit.kind("minecraft:stone_bricks","minecraft:air",true));assertEquals("occupied",ProjectionAudit.kind("minecraft:stone_bricks","minecraft:dirt",false));}
}
