package dev.twob2tkit.runtime.engine;

/** Emergency shelter must not indefinitely suppress survival and combat while it fails to close. */
final class BorerSurroundWait {
    static final int MAX_TICKS=30;
    private int started=-1;
    private float healthAtStart;
    private boolean suppressed;
    void reset(){started=-1;suppressed=false;}
    boolean allowed(){return !suppressed;}
    void started(int tick,float health){started=tick;healthAtStart=health;}
    boolean shouldAbort(boolean active,int tick,float health){
        if(!active){started=-1;return false;}
        if(started<0)return false;
        if(tick-started>=MAX_TICKS || health<healthAtStart-.1F){suppressed=true;started=-1;return true;}
        return false;
    }
}
