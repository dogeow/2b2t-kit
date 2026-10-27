package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class DecorationAttackPolicyTest {
 @Test void playersAnimalsNamedAndOccupiedDecorationsAreProtected(){
  for(String type:new String[]{"minecraft:painting","minecraft:item_frame","minecraft:glow_item_frame","minecraft:armor_stand"}){
   assertTrue(DecorationAttackPolicy.target(type,type,true,false,false,true));
   assertFalse(DecorationAttackPolicy.target(type,type,true,false,true,true));
   assertFalse(DecorationAttackPolicy.target(type,type,true,false,false,false));
   assertFalse(DecorationAttackPolicy.target(type,"minecraft:painting",true,true,false,true));
  }
  for(String type:new String[]{"minecraft:player","minecraft:wolf","minecraft:villager","minecraft:zombie"})assertFalse(DecorationAttackPolicy.target(type,type,true,false,false,true));
 }
}
