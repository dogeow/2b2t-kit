package dev.twob2tkit.trial;

import dev.twob2tkit.combat.HealthRecoveryWindow;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TrialGuardPolicyTest {
    private TrialGuardPolicy.Owner owner(boolean registered,boolean active,boolean death){
        return new TrialGuardPolicy.Owner(registered,active,death,"trial","run","/saves/trial","session","minecraft:overworld");
    }
    private TrialGuardPolicy.Scope scope(boolean local,boolean pve,String trial,String run,String world,String session,String dimension){
        return new TrialGuardPolicy.Scope(local,pve,trial,run,world,session,dimension);
    }
    private TrialGuardPolicy.Scope request(){return scope(true,true,"trial","run","/saves/trial","session","minecraft:overworld");}

    @Test void exactOptedInTrialCanObtainFoodAtTheActualDeadlockHealth(){
        var recovery=new HealthRecoveryWindow();
        assertTrue(recovery.hold(true,17.76667,false));
        boolean enabled=TrialGuardPolicy.healthRecoveryEnabled(true,owner(true,true,true),request());
        assertFalse(enabled);assertFalse(recovery.hold(enabled,17.76667,false));
        // A real combat/eating busy result is not replaced by this policy.
        boolean defending=true;assertFalse(recovery.hold(enabled,17.76667,defending));assertTrue(defending);
    }
    @Test void serverOtherSavePublishedCreativeAndHardcoreWorldsKeepOriginalHysteresis(){
        boolean[][] worlds={{false,true,false,true,false},{true,false,true,true,false},
                            {true,false,false,false,false},{true,false,false,true,true}};
        for(var world:worlds){
            boolean registered=SingleplayerTrialPolicy.world(world[0],world[1],world[2],world[3],world[4],"/saves/trial","/saves/trial");
            var recovery=new HealthRecoveryWindow();
            assertTrue(recovery.hold(TrialGuardPolicy.healthRecoveryEnabled(true,owner(registered,true,true),request()),17,false));
            assertTrue(recovery.hold(true,18.5,false));assertFalse(recovery.hold(true,19,false));
        }
        assertFalse(SingleplayerTrialPolicy.world(true,false,false,true,false,"/saves/other","/saves/trial"));
        assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,owner(false,true,true),request()));
    }
    @Test void everyIdentityFieldAndBothOptInFlagsAreRequired(){
        var wrong=new TrialGuardPolicy.Scope[]{
            scope(false,true,"trial","run","/saves/trial","session","minecraft:overworld"),
            scope(true,false,"trial","run","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"other","run","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"trial","old","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/other","session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/trial","old-session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/trial","session","minecraft:the_nether")};
        for(var request:wrong)assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,owner(true,true,true),request));
        assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,owner(true,false,true),request()));
        assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,owner(true,true,false),request()));
        assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,null,request()));
        assertTrue(TrialGuardPolicy.healthRecoveryEnabled(true,owner(true,true,true),null));
        assertFalse(TrialGuardPolicy.healthRecoveryEnabled(false,owner(false,false,false),null));
    }
    @Test void nativeChopRequiresTheCurrentActiveExactOwner(){
        assertTrue(TrialGuardPolicy.ownedChop(owner(true,true,true),request(),true,true));
        assertFalse(TrialGuardPolicy.ownedChop(owner(true,false,true),request(),true,true));
        assertFalse(TrialGuardPolicy.ownedChop(owner(false,true,true),request(),true,true));
        assertFalse(TrialGuardPolicy.ownedChop(owner(true,true,true),request(),false,true));
        assertFalse(TrialGuardPolicy.ownedChop(owner(true,true,true),request(),true,false));
        assertFalse(TrialGuardPolicy.ownedChop(owner(true,true,true),
            scope(true,true,"trial","old","/saves/trial","session","minecraft:overworld"),true,true));
    }
    @Test void crashedWorkerStillReleasesItsOwnChildButCannotStopAnotherRun(){
        var stopped=owner(true,false,true);
        assertTrue(TrialGuardPolicy.stopOwnedChop(stopped,request(),"trial","run",true,true));
        assertFalse(TrialGuardPolicy.stopOwnedChop(stopped,request(),"trial","other-run",true,true));
        assertFalse(TrialGuardPolicy.stopOwnedChop(stopped,request(),"other-trial","run",true,true));
        assertFalse(TrialGuardPolicy.stopOwnedChop(stopped,request(),"trial","run",false,true));
        assertFalse(TrialGuardPolicy.stopOwnedChop(stopped,
            scope(false,true,"trial","run","/saves/trial","session","minecraft:overworld"),"trial","run",true,true));
    }
    @Test void onlyFlightYieldsWhileOwnedChopIsActive(){
        assertFalse(TrialGuardPolicy.disableModule(true,true));
        assertTrue(TrialGuardPolicy.disableModule(true,false));
        assertTrue(TrialGuardPolicy.disableModule(false,true));
        assertTrue(TrialGuardPolicy.disableModule(false,false));
    }
    @Test void exactIdlePveGuardianCanBeginTrialCombatWithoutAnActiveChopper(){
        assertFalse(TrialGuardPolicy.ownedChop(owner(true,true,true),request(),false,false));
        assertTrue(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),request(),true,true,false));
        // Ownership admits the first combat tick; busy/Flight are separate lease decisions.
        assertFalse(TrialGuardPolicy.preserveGuardFlight(true,false,false));
        assertFalse(TrialGuardPolicy.preserveGuardFlight(true,false,true));
    }
    @Test void combatRequiresEveryLiveNativeIdentityAndOptInFlag(){
        var wrong=new TrialGuardPolicy.Scope[]{
            scope(false,true,"trial","run","/saves/trial","session","minecraft:overworld"),
            scope(true,false,"trial","run","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"other","run","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"trial","old","/saves/trial","session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/other","session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/trial","old-session","minecraft:overworld"),
            scope(true,true,"trial","run","/saves/trial","session","minecraft:the_nether"),
            scope(true,true,"trial","","/saves/trial","session","minecraft:overworld")};
        for(var guarded:wrong)assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),guarded,true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(false,true,true),request(),true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,false,true),request(),true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,false),request(),true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(null,request(),true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),null,true,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),request(),false,true,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),request(),true,false,false));
        assertFalse(TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),request(),true,true,true));
    }
    @Test void onlyAnActiveBusyCombatLeasePreservesFlightAndNeverOtherDisabledModules(){
        for(boolean owns:new boolean[]{false,true})for(boolean busy:new boolean[]{false,true})
            for(boolean flying:new boolean[]{false,true}){
                boolean preserve=TrialGuardPolicy.preserveGuardFlight(owns,busy,flying);
                assertEquals(owns&&busy&&flying,preserve);
                assertEquals(!preserve,TrialGuardPolicy.disableModule(true,false,preserve));
                assertTrue(TrialGuardPolicy.disableModule(false,false,preserve));
                assertTrue(TrialGuardPolicy.disableModule(false,true,preserve));
            }
        assertFalse(TrialGuardPolicy.disableModule(true,true,false),"Existing native chopper lease stays supported");
        boolean deadOwner=TrialGuardPolicy.ownsGuardCombat(owner(true,true,true),request(),true,false,false);
        assertFalse(TrialGuardPolicy.preserveGuardFlight(deadOwner,true,true));
    }
}
