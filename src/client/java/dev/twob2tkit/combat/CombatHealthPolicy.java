package dev.twob2tkit.combat;

/** Only a fully expired absorption buffer without injury evidence is ignored. */
final class CombatHealthPolicy {
    private CombatHealthPolicy() {}
    static boolean absorptionExpired(float previousBase,float previousAbsorption,float base,float absorption,
                                     boolean absorptionEffect,boolean injurySignal){
        return Float.isFinite(previousBase)&&Float.isFinite(previousAbsorption)&&Float.isFinite(base)
            &&Float.isFinite(absorption)&&previousBase>0&&previousAbsorption>0&&base>=previousBase
            &&absorption==0&&!absorptionEffect&&!injurySignal;
    }
}
