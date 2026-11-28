package dev.twob2tkit.automation;

/** Distinguish a user's mode changes from the native printer's temporary writes. */
final class PrinterExternalModeHistory {
    /** Pausing has no placement target; starting or restoring does. */
    static boolean requiresProjection(boolean enabled) { return enabled; }

    private Boolean observed,lastExternal;
    private long revision;
    private int writes;
    synchronized void observe(boolean value){
        if(writes>0)return;
        if(observed!=null&&observed!=value){revision++;lastExternal=value;}
        observed=value;
    }
    synchronized void written(boolean value){observed=value;}
    synchronized void beginWrite(){writes++;}
    synchronized void endWrite(){if(writes>0)writes--;}
    synchronized long revision(){return revision;}
    synchronized Boolean lastExternal(){return lastExternal;}
}
