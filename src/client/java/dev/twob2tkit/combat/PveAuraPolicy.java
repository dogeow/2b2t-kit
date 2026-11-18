package dev.twob2tkit.combat;
import java.util.Set;
import java.util.HashSet;
import java.util.function.Function;
public final class PveAuraPolicy {
 private PveAuraPolicy(){}
 private static final Set<String> HOSTILES=Set.of("zombie","zombie_villager","husk","drowned","skeleton","stray","bogged","wither_skeleton","creeper","spider","cave_spider","slime","magma_cube","witch","phantom","silverfish","endermite","blaze","ghast","piglin_brute","pillager","vindicator","evoker","vex","ravager","guardian","elder_guardian");
 public static boolean allowed(String id){return id!=null&&id.startsWith("minecraft:")&&HOSTILES.contains(id.substring(10));}
 /** Preserve the user's zombified-piglin choice while retaining hostile-only defaults. */
 public static <T> Set<T> targets(Iterable<T> all, Set<?> selected, Function<T,String> idOf){
  Set<T> result=new HashSet<>();
  for(T type:all){String id=idOf.apply(type);if(allowed(id)||"minecraft:zombified_piglin".equals(id)&&selected.contains(type))result.add(type);}
  return result;
 }
 public static boolean filterPassiveForPiglin(String id,boolean piglinNearby){
  return piglinNearby && ("minecraft:piglin".equals(id)||"minecraft:zombified_piglin".equals(id));
 }
}
