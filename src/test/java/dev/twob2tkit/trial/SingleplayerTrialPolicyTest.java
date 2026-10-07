package dev.twob2tkit.trial;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class SingleplayerTrialPolicyTest {
    @Test void onlyTheRegisteredUnpublishedSurvivalSaveCanAct(){
        assertTrue(SingleplayerTrialPolicy.world(true,false,false,true,false,"/saves/trial","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(false,true,false,true,false,"/saves/trial","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(true,false,true,true,false,"/saves/trial","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(true,false,false,false,false,"/saves/trial","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(true,false,false,true,true,"/saves/trial","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(true,false,false,true,false,"/saves/other","/saves/trial"));
        assertFalse(SingleplayerTrialPolicy.world(true,false,false,true,false,"",""));
    }
    @Test void requestsCannotBorrowAnotherRunOrReplayADeath(){
        assertTrue(SingleplayerTrialPolicy.owner("trial","run","trial","run"));
        assertFalse(SingleplayerTrialPolicy.owner("trial","old","trial","new"));
        assertTrue(SingleplayerTrialPolicy.respawn(true,true,true,2,2,1,1500));
        assertFalse(SingleplayerTrialPolicy.respawn(true,true,true,2,2,2,1500));
        assertFalse(SingleplayerTrialPolicy.respawn(true,true,true,2,2,1,500));
        assertFalse(SingleplayerTrialPolicy.respawn(false,true,true,2,2,1,1500));
    }
}
