package dev.twob2tkit.combat;

/** Hysteresis: after injury, work waits for recovery; combat retains movement priority. */
public final class HealthRecoveryWindow {
    private boolean recovering;
    public boolean hold(boolean enabled,double health,boolean defending){
        if(!enabled){recovering=false;return false;}
        if(health<18)recovering=true;
        if(health>=19)recovering=false;
        return recovering&&!defending;
    }
}
