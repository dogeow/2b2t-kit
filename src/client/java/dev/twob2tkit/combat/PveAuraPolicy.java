package dev.twob2tkit.combat;
import java.util.Set;
public final class PveAuraPolicy {
 private PveAuraPolicy(){}
 private static final Set<String> HOSTILES=Set.of("zombie","zombie_villager","husk","drowned","skeleton","stray","bogged","wither_skeleton","creeper","spider","cave_spider","slime","magma_cube","witch","phantom","silverfish","endermite","blaze","ghast","piglin_brute","pillager","vindicator","evoker","vex","ravager","guardian","elder_guardian");
 public static boolean allowed(String id){return id!=null&&id.startsWith("minecraft:")&&HOSTILES.contains(id.substring(10));}
}
