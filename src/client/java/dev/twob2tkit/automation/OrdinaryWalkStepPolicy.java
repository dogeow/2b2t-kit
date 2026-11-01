package dev.twob2tkit.automation;

/** Ordinary walking is a supported bounded step, never an implicit flight-off descent. */
final class OrdinaryWalkStepPolicy {
    private OrdinaryWalkStepPolicy(){}
    static boolean boundedStep(double origin,double target){
        return Double.isFinite(origin)&&Double.isFinite(target)&&Math.abs(origin-target)<=1.100001;
    }
    static boolean withinEnvelope(double origin,double target,double actual){
        return Double.isFinite(origin)&&Double.isFinite(target)&&Double.isFinite(actual)
            &&actual>=Math.min(origin,target)-1.5&&actual<=Math.max(origin,target)+1.5;
    }
}
