package dev.twob2tkit.automation;
/** Wait for a late inventory update without repeating a potentially successful click. */
final class CraftConfirmation {
    private int waiting;
    void reset(){waiting=0;}
    boolean ready(boolean matches,String reason){
        if(matches){waiting=0;return true;}
        if(++waiting>80)throw new IllegalStateException(reason+" (server confirmation timeout)");
        return false;
    }
}
