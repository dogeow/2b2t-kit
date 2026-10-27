package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class EmptyBoatRecoveryPolicyTest {
    @Test void walls_do_not_invalidate_an_empty_grounded_owned_recovery(){
        assertTrue(EmptyBoatRecoveryPolicy.allowed(true,true,true,true,true,true,true,true,true,true,true,true,2.4,3));
    }
    @Test void passengers_foreign_leash_named_boat_damage_ui_missing_space_or_threats_refuse(){
        for(int i=0;i<12;i++){
            boolean[] a=new boolean[12];java.util.Arrays.fill(a,true);a[i]=false;
            assertFalse(EmptyBoatRecoveryPolicy.allowed(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7],a[8],a[9],a[10],a[11],2.4,3));
        }
        assertFalse(EmptyBoatRecoveryPolicy.allowed(true,true,true,true,true,true,true,true,true,true,true,true,2.81,3));
        assertFalse(EmptyBoatRecoveryPolicy.allowed(true,true,true,true,true,true,true,true,true,true,true,true,Double.NaN,3));
    }
    @Test void old_or_future_requests_and_stale_status_never_attack(){
        assertTrue(EmptyBoatRecoveryPolicy.fresh(2000,1500,3000,1900));
        assertFalse(EmptyBoatRecoveryPolicy.fresh(2000,999,3000,1900));
        assertFalse(EmptyBoatRecoveryPolicy.fresh(2000,2100,3000,1900));
        assertFalse(EmptyBoatRecoveryPolicy.fresh(2000,1500,2000,1900));
        assertFalse(EmptyBoatRecoveryPolicy.fresh(2000,1500,7000,1900));
        assertFalse(EmptyBoatRecoveryPolicy.fresh(2000,1500,3000,999));
    }
}
