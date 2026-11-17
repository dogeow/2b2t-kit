package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;
class FarmStationPolicyTest {
 boolean scope(String server,long expiry,boolean sameInput,boolean revision,double hp,boolean autoLog){return FarmStationPolicy.scope(server,"simpcraft.com",true,true,10000,expiry,20,true,sameInput,revision,hp,20,false,false,false,autoLog);}
 @Test void explicitCurrentServerOnly(){assertTrue(scope("simpcraft.com",20000,true,true,20,true));assertFalse(scope("other.server",20000,true,true,20,true));}
 @Test void relayRequiresTheExactCurrentEndpoint(){
  var relay="127.0.0.1:25566";
  assertTrue(FarmStationPolicy.scope(relay,relay,true,true,10000,20000,20,true,true,true,20,20,false,false,false,true));
  assertFalse(scope(relay,20000,true,true,20,true));
  assertFalse(FarmStationPolicy.acceptsEndpoint("127.0.0.1:25565"));
 }
 @Test void staleAndManualIntentsNeverResume(){assertFalse(scope("simpcraft.com",9999,true,true,20,true));assertFalse(scope("simpcraft.com",20000,false,true,20,true));assertFalse(scope("simpcraft.com",20000,true,false,20,true));assertFalse(scope("simpcraft.com",2000000,true,true,20,true));}
 @Test void nativeProtectionRemainsRequired(){assertFalse(scope("simpcraft.com",20000,true,true,18,true));assertFalse(scope("simpcraft.com",20000,true,true,20,false));assertFalse(scope("simpcraft.com",20000,true,true,Double.NaN,true));}
 @Test void groundedStationNotOldFloatingPoint(){assertTrue(FarmStationPolicy.station(.5,163,.5,.5,163,.5,true,false));assertFalse(FarmStationPolicy.station(.5,165,.5,.5,163,.5,false,true));}
 @Test void hoverMeleeRequiresExactPoseShortIntentAndUncontestedGuard(){
  assertTrue(FarmStationPolicy.hoverMelee(.5,209.22,.5,.5,209.22,.5,true,false,15000,true,false,false));
  assertFalse(FarmStationPolicy.hoverMelee(.5,209.22,.5,.5,209.22,.5,true,false,15001,true,false,false));
  assertFalse(FarmStationPolicy.hoverMelee(.5,209.22,.5,.5,209.22,.5,true,false,10000,true,true,false));
  assertFalse(FarmStationPolicy.hoverMelee(.5,209.22,.5,.5,209.22,.5,true,false,10000,true,false,true));
  assertFalse(FarmStationPolicy.hoverMelee(.8,209.22,.5,.5,209.22,.5,true,false,10000,true,false,false));
 }
 @Test void hoverMeleeOnlyAdmitsVisibleAdultPiglinsInTheGapBelow(){
  assertTrue(FarmStationPolicy.hoverTarget(.1,3.22,true,true,true));
  assertFalse(FarmStationPolicy.hoverTarget(.1,2.8,true,true,true));
  assertFalse(FarmStationPolicy.hoverTarget(.1,3.22,false,true,true));
  assertFalse(FarmStationPolicy.hoverTarget(.1,3.22,true,false,true));
 }
 @Test void nearestMeleeAndOtherPlayersPreventArrows(){assertFalse(FarmStationPolicy.lure(true,true,false,true,30,14,0,4));assertFalse(FarmStationPolicy.lure(true,false,true,true,30,14,0,4));assertTrue(FarmStationPolicy.lure(true,false,false,true,30,14,0,4));}
 @Test void arrowsHavePersistentBoundAndRange(){assertFalse(FarmStationPolicy.lure(true,false,false,true,49,14,0,4));assertFalse(FarmStationPolicy.lure(true,false,false,true,30,0,0,4));assertFalse(FarmStationPolicy.lure(true,false,false,true,30,14,4,100));}
 @Test void ourArrowBelowTheEyeTravellingDownwardIsNotAnIncomingThreat(){assertFalse(FarmStationPolicy.incoming(false,2,-1,0,-.2,.1,0));assertFalse(FarmStationPolicy.incoming(true,-2,1,0,-.2,.1,0));}
 @Test void hostileFireballClosingOnTheEyesRemainsAThreat(){assertTrue(FarmStationPolicy.incoming(false,-1,0,0,-10,0,0));assertFalse(FarmStationPolicy.incoming(false,1,0,0,-10,0,0));assertFalse(FarmStationPolicy.incoming(false,0,0,0,-10,0,0));}
 @Test void meteorRestartingTheNextDrawStillEndsTheFirstSingleShot(){assertTrue(FarmStationPolicy.released(20,true,1));assertFalse(FarmStationPolicy.released(20,true,20));assertFalse(FarmStationPolicy.released(17,true,0));}
 @Test void onlyOneDrawReleaseIsConsideredObserved(){assertFalse(FarmStationPolicy.released(17,false));assertFalse(FarmStationPolicy.released(20,true));assertTrue(FarmStationPolicy.released(20,false));}
}
