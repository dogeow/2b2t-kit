package dev.twob2tkit.builder;

import java.util.Set;

/** A supervisor can adjust the current job, never silently restart a stopped/manual job. */
public final class BuildSupervisionPolicy {
    private BuildSupervisionPolicy() {}
    public static boolean maySupply(boolean sameSession,boolean active,String outcome,boolean safe){
        return sameSession && !active && Set.of("missing_materials","blocked").contains(outcome) && safe;
    }
    public static boolean mayResumeSupply(String outcome,boolean gainedNeededItems){return outcome.equals("missing_materials") || outcome.equals("blocked")&&gainedNeededItems;}
    public static boolean mayApply(String action,boolean sameSession,boolean active,boolean loading,
                                   boolean queueSettled,boolean safe,int sinceLastAction) {
        if(!sameSession || !active || !safe || sinceLastAction<100)return false;
        if(action.equals("pause_and_report"))return true;
        return Set.of("rescan","replan").contains(action) && !loading && queueSettled;
    }
}
