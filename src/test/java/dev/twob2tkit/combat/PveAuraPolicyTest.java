package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PveAuraPolicyTest{
 @Test void protectsAgainstApproachingHostiles(){for(var id:new String[]{"creeper","skeleton","zombie","witch","phantom","spider"})assertTrue(PveAuraPolicy.allowed("minecraft:"+id));}
 @Test void neverTargetsPlayersLivestockOrNeutralMobs(){for(var id:new String[]{"player","cow","pig","chicken","sheep","villager","wolf","cat","piglin","zombified_piglin","enderman","iron_golem"})assertFalse(PveAuraPolicy.allowed("minecraft:"+id));}
 @Test void rejectsUnknownNamespacesAndNull(){assertFalse(PveAuraPolicy.allowed(null));assertFalse(PveAuraPolicy.allowed("mod:creeper"));}
 @Test void preservesOnlyAnExplicitZombifiedPiglinSelection(){
  var all=java.util.List.of("minecraft:zombie","minecraft:zombified_piglin","minecraft:player");
  assertEquals(java.util.Set.of("minecraft:zombie","minecraft:zombified_piglin"),PveAuraPolicy.targets(all,java.util.Set.of("minecraft:zombified_piglin","minecraft:player"),x->x));
  assertEquals(java.util.Set.of("minecraft:zombie"),PveAuraPolicy.targets(all,java.util.Set.of(),x->x));
 }
 @Test void passiveFilterMayBeBorrowedOnlyForANearbyPiglinTarget(){
  assertTrue(PveAuraPolicy.filterPassiveForPiglin("minecraft:zombified_piglin",true));
  assertTrue(PveAuraPolicy.filterPassiveForPiglin("minecraft:piglin",true));
  assertFalse(PveAuraPolicy.filterPassiveForPiglin("minecraft:zombified_piglin",false));
  assertFalse(PveAuraPolicy.filterPassiveForPiglin("minecraft:zombie",true));
 }
}
