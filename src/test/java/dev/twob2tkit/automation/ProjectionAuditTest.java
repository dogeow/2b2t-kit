package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionAuditTest {
 @Test void aDoorStateDifferenceIsNotANewDoor(){assertEquals("state_only",ProjectionAudit.kind("minecraft:oak_door","minecraft:oak_door",false));}
 @Test void missingAndOccupiedRequireDifferentWorkflows(){assertEquals("missing",ProjectionAudit.kind("minecraft:stone_bricks","minecraft:air",true));assertEquals("occupied",ProjectionAudit.kind("minecraft:stone_bricks","minecraft:dirt",false));}
 @Test void actualModelAndNeighborReadsUseTheServerChunkBoundary()throws Exception{
  String source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProjectionAudit.java"));
  assertFalse(source.contains(".hasChunk("));assertFalse(source.contains(".hasChunkAt("));
  assertTrue(source.contains("LoadedServerChunkEvidence.isServerChunk(c.level,chunk)"));
  assertTrue(source.contains("ChunkStatus.FULL,false"));
  assertEquals(2,source.split(java.util.regex.Pattern.quote("if(!serverChunk(c,p))"),-1).length-1);
  assertTrue(source.contains("serverChunk(c,p.relative(d))"));
  assertTrue(source.contains("loaded_server_chunks_verified"));
 }
}
