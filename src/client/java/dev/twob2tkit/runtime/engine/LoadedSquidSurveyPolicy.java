package dev.twob2tkit.runtime.engine;

final class LoadedSquidSurveyPolicy {
    private LoadedSquidSurveyPolicy(){}
    static boolean target(String type,boolean alive,boolean removed,boolean named,float health,double y){
        return "minecraft:squid".equals(type)&&alive&&!removed&&!named
            &&Float.isFinite(health)&&health>0&&Double.isFinite(y)&&y>=50&&y<=64;
    }
    static boolean glowTarget(String type,boolean alive,boolean removed,boolean named,float health,double y){
        return "minecraft:glow_squid".equals(type)&&alive&&!removed&&!named
            &&Float.isFinite(health)&&health>0&&Double.isFinite(y)&&y>=-64&&y<320;
    }
}
