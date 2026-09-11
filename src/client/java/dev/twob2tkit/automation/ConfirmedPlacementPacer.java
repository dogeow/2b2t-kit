package dev.twob2tkit.automation;

/** One proposal at a time. Plain cubes may advance sooner only after the exact server acknowledgement. */
public final class ConfirmedPlacementPacer {
    public static final int FAST_PERIOD=8, LEGACY_PERIOD=20, TIMEOUT=60;
    private final int simplePeriod;
    public ConfirmedPlacementPacer(){this(true);}
    public ConfirmedPlacementPacer(boolean accelerated){simplePeriod=accelerated?FAST_PERIOD:LEGACY_PERIOD;}
    private int queuedAt=-LEGACY_PERIOD,nextAttempt,sentAt=-1;
    private boolean simple,confirmed,sent;
    public boolean acquire(int tick,boolean paused,boolean queueIdle){
        if(paused||!queueIdle||tick<nextAttempt)return false;
        if(simple){if(!confirmed||tick-queuedAt<simplePeriod)return false;}
        else if(tick-queuedAt<LEGACY_PERIOD)return false;
        nextAttempt=tick+2;return true;
    }
    public void queued(int tick,boolean safeSimple){queuedAt=tick;nextAttempt=tick+1;simple=safeSimple;confirmed=sent=false;sentAt=-1;}
    public void sent(int tick){if(simple&&!sent){sent=true;sentAt=tick;}}
    public boolean acknowledge(){if(!simple||!sent||confirmed)return false;confirmed=true;return true;}
    public boolean cancelUnsent(int tick){if(sent)return false;simple=confirmed=false;queuedAt=tick-LEGACY_PERIOD;nextAttempt=tick;return true;}
    public boolean awaiting(){return simple&&!confirmed;}
    public boolean sent(){return sent;}
    public int age(int tick){return tick-(sentAt<0?queuedAt:sentAt);}
    public boolean timedOut(int tick){return awaiting()&&age(tick)>=TIMEOUT;}
    public static boolean safeSimple(boolean noProperties,boolean fullCube,boolean falling,boolean blockEntity){return noProperties&&fullCube&&!falling&&!blockEntity;}
}
