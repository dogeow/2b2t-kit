package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SingleBlockServerConfirmationTest {
    private SingleBlockServerConfirmation<String,String> begin(boolean underwater) {
        var proof=new SingleBlockServerConfirmation<String,String>();
        proof.begin("world","request","target",state->state.equals("air")||underwater&&state.equals("water"));
        return proof;
    }
    private void sent(SingleBlockServerConfirmation<String,String> p) { p.sent("world","request","target",7); }
    private boolean done(SingleBlockServerConfirmation<String,String> p,String state,boolean pending) {
        return p.confirmed("world","request","target",state,pending);
    }
    private void packet(SingleBlockServerConfirmation<String,String> p,String state) {
        p.serverBlock("world","request","target",state);
    }
    private void ack(SingleBlockServerConfirmation<String,String> p,int sequence) {
        p.serverAck("world","request","target",sequence);
    }

    @Test void predictedAirNeverCreditsCompletionAndLocksFurtherNativeMining() {
        var p=begin(false);sent(p);p.clientState("world","request","target","air");
        assertTrue(p.hold("world","request","target"));assertFalse(done(p,"air",false));
        ack(p,7);assertFalse(done(p,"air",false));
    }
    @Test void aServerPacketNeedsTheCurrentNativeAckAndCorrectedClientState() {
        var p=begin(false);sent(p);packet(p,"air");
        assertFalse(done(p,"air",false));ack(p,6);assertFalse(done(p,"air",false));
        ack(p,7);assertFalse(done(p,"air",true));assertFalse(done(p,"stone",false));
        assertTrue(done(p,"air",false));
    }
    @Test void deferredPacketMayBeConfirmedAfterVanillaPredictionCorrection() {
        var p=begin(false);sent(p);packet(p,"air");ack(p,7);
        assertFalse(done(p,"stone",true));assertTrue(done(p,"air",false));
    }
    @Test void latestStopSequenceMustBeAcknowledgedEvenIfStartWasAlreadyAcknowledged() {
        var p=begin(false);sent(p);ack(p,7);p.sent("world","request","target",9);
        packet(p,"air");assertFalse(done(p,"air",false));ack(p,9);assertTrue(done(p,"air",false));
    }
    @Test void rejectionAndLaterRollbackRevokeSuccessWithoutReopeningTheNativeAttempt() {
        var p=begin(false);sent(p);p.clientState("world","request","target","air");
        packet(p,"air");ack(p,7);assertTrue(done(p,"air",false));
        packet(p,"stone");assertFalse(done(p,"stone",false));
        p.clientState("world","request","target","stone");assertTrue(p.hold("world","request","target"));
    }
    @Test void timeoutOrStopRetainsAnUncertainCellClaimButAllowsWorkAtAnotherCell() {
        var p=begin(false);sent(p);p.close("request",false);
        assertThrows(IllegalStateException.class,()->p.begin("world","retry","target",s->s.equals("air")));
        p.begin("world","different","other",s->s.equals("air"));
    }
    @Test void confirmedCompletionAndUnsentPreflightReleaseTheirClaims() {
        var p=begin(false);sent(p);packet(p,"air");ack(p,7);
        p.close("request",done(p,"air",false));p.begin("world","next","target",s->s.equals("air"));
        p.close("next",false);p.begin("world","unsent-next","target",s->s.equals("air"));
    }
    @Test void wrongWorldRequestTargetEarlyAndAfterClosePacketsCannotAcknowledge() {
        var p=begin(false);packet(p,"air");ack(p,7);sent(p);assertFalse(done(p,"air",false));
        p.serverBlock("old-world","request","target","air");
        p.serverBlock("world","old-request","target","air");
        p.serverBlock("world","request","other","air");
        p.serverAck("world","old-request","target",99);assertFalse(done(p,"air",false));
        packet(p,"air");assertFalse(done(p,"air",false));ack(p,7);assertTrue(done(p,"air",false));
        p.close("request",true);packet(p,"air");ack(p,99);assertFalse(done(p,"air",false));
    }
    @Test void waterOnlyCountsForExplicitUnderwaterGravelAndNeverForWaterloggedSolids() {
        var dry=begin(false);sent(dry);packet(dry,"water");ack(dry,7);assertFalse(done(dry,"water",false));
        var wet=begin(true);sent(wet);packet(wet,"water");ack(wet,7);assertTrue(done(wet,"water",false));
        packet(wet,"waterlogged-solid");assertFalse(done(wet,"waterlogged-solid",false));
        for(boolean optedIn:new boolean[]{false,true}){
            assertTrue(SingleBlockRemovalPolicy.removed(true,false,optedIn));
            assertFalse(SingleBlockRemovalPolicy.removed(false,false,optedIn));
        }
        assertTrue(SingleBlockRemovalPolicy.removed(false,true,true));
        assertFalse(SingleBlockRemovalPolicy.removed(false,true,false));
    }
    @Test void newWorldCannotReuseAnOldRequestAckAndMalformedOrCompetingOwnersAreRejected() {
        var p=begin(false);sent(p);p.close("request",false);
        p.begin("new-world","new","target",s->s.equals("air"));p.sent("new-world","new","target",1);
        p.serverBlock("world","request","target","air");p.serverAck("world","request","target",99);
        assertFalse(p.confirmed("new-world","new","target","air",false));
        assertThrows(IllegalStateException.class,()->p.begin("new-world","other","other",s->true));
        assertThrows(IllegalArgumentException.class,()->new SingleBlockServerConfirmation<String,String>().begin("","id","p",s->true));
    }
}
