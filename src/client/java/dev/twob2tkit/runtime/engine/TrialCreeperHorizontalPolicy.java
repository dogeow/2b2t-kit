package dev.twob2tkit.runtime.engine;

import java.util.List;

/** Reversible work deferral for currently observed ordinary creepers in an opted-in local trial. */
final class TrialCreeperHorizontalPolicy {
    static final double SAFE_DISTANCE = 16;
    record Threat(boolean current,boolean alive,boolean ordinaryCreeper,boolean powered,boolean ignited,
                  boolean swelling,boolean loadedFinite,double feetDistance,double bodyDistance) {}
    static boolean safe(boolean authorized,boolean standalone,boolean missingRestored,
                        boolean groundedDryClear,boolean nearbyHostile,List<Threat> unresolved) {
        return authorized&&standalone&&!missingRestored&&groundedDryClear&&!nearbyHostile
            &&unresolved!=null&&!unresolved.isEmpty()&&unresolved.stream().allMatch(t->t!=null&&t.current()
                &&t.alive()&&t.ordinaryCreeper()&&!t.powered()&&!t.ignited()&&!t.swelling()&&t.loadedFinite()
                &&Double.isFinite(t.feetDistance())&&Double.isFinite(t.bodyDistance())
                &&t.feetDistance()>=SAFE_DISTANCE&&t.bodyDistance()>=SAFE_DISTANCE);
    }
    private TrialCreeperHorizontalPolicy() {}
}
