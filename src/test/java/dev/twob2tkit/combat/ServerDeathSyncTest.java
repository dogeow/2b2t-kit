package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ServerDeathSyncTest {
 @Test void oldNetherRecordCannotMatchNewOverworldDeath(){assertFalse(ServerDeathSync.sameBlock("minecraft:the_nether",10,64,20,"minecraft:overworld",10,64,20));}
 @Test void detailedClientLocationMatchesServersBlockWithoutLosingTheClientDeathTime(){assertTrue(ServerDeathSync.sameBlock("minecraft:overworld",10.7,64.8,-20.3,"minecraft:overworld",10,64,-21));}
 @Test void differentPositionsRequireFreshServerRecord(){assertFalse(ServerDeathSync.sameBlock("minecraft:overworld",10,64,20,"minecraft:overworld",11,64,20));}
}
