package dev.twob2tkit.runtime.engine;
final class GuardWeaponPolicy {
    static boolean usableBow(boolean bow,boolean damageable,int remaining){return bow&&(!damageable||remaining>=8);}
    static boolean needsRise(double feet,double mobFeet){return feet<mobFeet+3.0;}
    enum Hover{RISE,HOLD,FALLBACK}
    static Hover hover(double feet,double mobFeet,boolean wholeColumnClear){
        if(feet>mobFeet+3.4)return Hover.FALLBACK;
        if(needsRise(feet,mobFeet))return wholeColumnClear?Hover.RISE:Hover.FALLBACK;
        return Hover.HOLD;
    }
    private GuardWeaponPolicy(){}
}
