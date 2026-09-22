package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PveAuraPolicyTest{
 @Test void protectsAgainstApproachingHostiles(){for(var id:new String[]{"creeper","skeleton","zombie","witch","phantom","spider"})assertTrue(PveAuraPolicy.allowed("minecraft:"+id));}
 @Test void neverTargetsPlayersLivestockOrNeutralMobs(){for(var id:new String[]{"player","cow","pig","chicken","sheep","villager","wolf","cat","piglin","zombified_piglin","enderman","iron_golem"})assertFalse(PveAuraPolicy.allowed("minecraft:"+id));}
 @Test void rejectsUnknownNamespacesAndNull(){assertFalse(PveAuraPolicy.allowed(null));assertFalse(PveAuraPolicy.allowed("mod:creeper"));}
}
