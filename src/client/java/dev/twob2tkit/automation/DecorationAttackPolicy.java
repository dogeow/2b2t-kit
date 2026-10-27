package dev.twob2tkit.automation;
import java.util.Set;
final class DecorationAttackPolicy {
 private DecorationAttackPolicy(){}
 static boolean target(String actual,String expected,boolean alive,boolean removed,boolean named,boolean empty){
  return Set.of("minecraft:painting","minecraft:item_frame","minecraft:glow_item_frame","minecraft:armor_stand").contains(actual)
      &&actual.equals(expected)&&alive&&!removed&&!named&&empty;
 }
}
