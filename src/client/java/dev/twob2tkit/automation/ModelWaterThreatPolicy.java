package dev.twob2tkit.automation;
/** Only distant occluded ordinary threats can coexist with a guarded original-source action. */
final class ModelWaterThreatPolicy {
 static boolean permit(String type,boolean current,boolean visible,double distanceSquared,boolean neutralEnderman){
  if(!current||visible||!Double.isFinite(distanceSquared))return false;
  if(type.equals("minecraft:enderman"))return neutralEnderman&&distanceSquared>=64;
  if(java.util.Set.of("minecraft:skeleton","minecraft:bogged").contains(type))return distanceSquared>=144;
  return java.util.Set.of("minecraft:zombie","minecraft:slime","minecraft:spider","minecraft:cave_spider").contains(type)&&distanceSquared>=64;
 }
}
