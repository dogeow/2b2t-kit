package dev.twob2tkit.fisher;

/** Idle fishing never adopts a chest and never moves a displaced player back. */
public final class IdleFishingPolicy {
    public enum Decision { NORMAL, FISH, STOP_FULL, STOP_CHANGED }
    private IdleFishingPolicy() {}
    public static Decision decide(boolean scoped,boolean fishingPhase,boolean inventoryFull,double horizontal,double vertical){
        if(!scoped)return Decision.NORMAL;
        if(!fishingPhase||!Double.isFinite(horizontal)||!Double.isFinite(vertical)||horizontal<0||vertical<0||horizontal>.45||vertical>.45)
            return Decision.STOP_CHANGED;
        return inventoryFull?Decision.STOP_FULL:Decision.FISH;
    }
    public static int chestRange(int preference){return Math.max(2,Math.min(8,preference));}
    public static boolean mayDeposit(boolean active,boolean scoped){return active&&!scoped;}
}
