package dev.twob2tkit.builder;

/** Debounce confirmed local completion; blocked/unknown actions keep the old retry allowance. */
public final class BuildDeparturePolicy {
    public static final int QUIET_TICKS=6, RETRY_TICKS=100;
    private int emptySince=-1;
    public void reset(){emptySince=-1;}
    public boolean observe(int tick,boolean queueSettled,boolean localWork){
        if(!queueSettled||localWork){reset();return false;}
        if(emptySince<0||tick<emptySince)emptySince=tick;
        return tick-emptySince>=QUIET_TICKS;
    }
}
