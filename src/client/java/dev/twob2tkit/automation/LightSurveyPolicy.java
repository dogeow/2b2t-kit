package dev.twob2tkit.automation;

/** Classification of real light-layer readings and vanilla zombie geometry.
 * A block-light risk is a lighting candidate, not a complete server spawn roll.
 * Sky/time, difficulty, mob caps, players, biomes and special spawn rules remain
 * outside this predicate. In particular it makes no claim about every mob.
 */
public final class LightSurveyPolicy {
    private LightSurveyPolicy() {}
    public record Sample(int blockLight,int skyLight,int spawnBlockLight,int spawnSkyLight,
                         boolean zombieSpawnFloor,boolean zombieBlockLightRisk) {}

    public static Sample sample(int blockLight,int skyLight,int spawnBlockLight,int spawnSkyLight,
                                boolean vanillaZombieGeometry,int monsterBlockLightLimit){
        for(int value:new int[]{blockLight,skyLight,spawnBlockLight,spawnSkyLight,monsterBlockLightLimit})
            if(value<0||value>15)throw new IllegalArgumentException("Light values must be actual0..15 readings");
        return new Sample(blockLight,skyLight,spawnBlockLight,spawnSkyLight,vanillaZombieGeometry,
            vanillaZombieGeometry&&spawnBlockLight<=monsterBlockLightLimit);
    }
}
