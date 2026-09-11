package dev.twob2tkit.runtime.engine;

/** Nearby creepers threaten the structure even when the player is hovering above them. */
final class StandaloneCreeperPolicy {
    private StandaloneCreeperPolicy() {}
    static boolean alert(boolean visible,boolean swelling,boolean powered,double distance){
        return visible&&distance<=(powered?12:8) || swelling&&distance<=(powered?14:8) || distance<=4;
    }
    static boolean evade(boolean swelling,boolean powered,double distance,boolean alreadyEvading){
        double margin=powered?12:8;
        return distance<(alreadyEvading?margin:powered?10:6) || swelling&&distance<margin;
    }
    static boolean riseMovesAway(double playerY,double creeperY){return playerY>=creeperY;}
}
