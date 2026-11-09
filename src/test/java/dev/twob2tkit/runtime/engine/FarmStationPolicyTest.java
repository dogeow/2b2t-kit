package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;
class FarmStationPolicyTest {
 boolean scope(String server,long expiry,boolean sameInput,boolean revision,double hp,boolean autoLog){return FarmStationPolicy.scope(server,"simpcraft.com",true,true,10000,expiry,20,true,sameInput,revision,hp,20,false,false,false,autoLog);}
 @Test void explicitCurrentServerOnly(){assertTrue(scope("simpcraft.com",20000,true,true,20,true));assertFalse(scope("other.server",20000,true,true,20,true));}
 @Test void staleAndManualIntentsNeverResume(){assertFalse(scope("simpcraft.com",9999,true,true,20,true));assertFalse(scope("simpcraft.com",20000,false,true,20,true));assertFalse(scope("simpcraft.com",20000,true,false,20,true));assertFalse(scope("simpcraft.com",2000000,true,true,20,true));}
 @Test void nativeProtectionRemainsRequired(){assertFalse(scope("simpcraft.com",20000,true,true,18,true));assertFalse(scope("simpcraft.com",20000,true,true,20,false));assertFalse(scope("simpcraft.com",20000,true,true,Double.NaN,true));}
 @Test void groundedStationNotOldFloatingPoint(){assertTrue(FarmStationPolicy.station(.5,163,.5,.5,163,.5,true,false));assertFalse(FarmStationPolicy.station(.5,165,.5,.5,163,.5,false,true));}
 @Test void nearestMeleeAndOtherPlayersPreventArrows(){assertFalse(FarmStationPolicy.lure(true,true,false,true,30,14,0,4));assertFalse(FarmStationPolicy.lure(true,false,true,true,30,14,0,4));assertTrue(FarmStationPolicy.lure(true,false,false,true,30,14,0,4));}
 @Test void arrowsHavePersistentBoundAndRange(){assertFalse(FarmStationPolicy.lure(true,false,false,true,49,14,0,4));assertFalse(FarmStationPolicy.lure(true,false,false,true,30,0,0,4));assertFalse(FarmStationPolicy.lure(true,false,false,true,30,14,4,100));}
 @Test void ourArrowBelowTheEyeTravellingDownwardIsNotAnIncomingThreat(){assertFalse(FarmStationPolicy.incoming(false,2,-1,0,-.2,.1,0));assertFalse(FarmStationPolicy.incoming(true,-2,1,0,-.2,.1,0));}
 @Test void hostileFireballClosingOnTheEyesRemainsAThreat(){assertTrue(FarmStationPolicy.incoming(false,-1,0,0,-10,0,0));assertFalse(FarmStationPolicy.incoming(false,1,0,0,-10,0,0));assertFalse(FarmStationPolicy.incoming(false,0,0,0,-10,0,0));}
 @Test void meteorRestartingTheNextDrawStillEndsTheFirstSingleShot(){assertTrue(FarmStationPolicy.released(20,true,1));assertFalse(FarmStationPolicy.released(20,true,20));assertFalse(FarmStationPolicy.released(17,true,0));}
 @Test void onlyOneDrawReleaseIsConsideredObserved(){assertFalse(FarmStationPolicy.released(17,false));assertFalse(FarmStationPolicy.released(20,true));assertTrue(FarmStationPolicy.released(20,false));}
}
