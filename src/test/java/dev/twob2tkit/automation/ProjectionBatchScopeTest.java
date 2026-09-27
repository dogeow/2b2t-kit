package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionBatchScopeTest {
    private final ProjectionBatchScope.Owner own=new ProjectionBatchScope.Owner("lease","task","world","projection");
    private final ProjectionBatchScope<String> scope=new ProjectionBatchScope<>();
    @Test void defaultIsUnrestrictedButAnEmptyBatchAllowsNothing(){
        assertTrue(scope.allows(null,"portal"));scope.set(own,List.of(),p->true);
        assertTrue(scope.active());assertEquals(0,scope.count());assertFalse(scope.allows(own,"portal"));
    }
    @Test void installedBatchRejectsExcludedPortalUntilExplicitClear(){
        scope.set(own,List.of("inside"),p->true);
        assertTrue(scope.allows(own,"inside"));assertFalse(scope.allows(own,"portal"));
        // No request-file presence or TTL is consulted by allows: deleting a consumed file cannot open the mask.
        for(int i=0;i<100;i++)assertFalse(scope.allows(own,"portal"));
        scope.clear(own);assertFalse(scope.active());assertTrue(scope.allows(null,"portal"));
    }
    @Test void invalidAtomicReplacementKeepsOriginalMask(){
        scope.set(own,List.of("inside"),p->true);
        assertThrows(IllegalArgumentException.class,()->scope.set(own,List.of("new","outside"),p->!p.equals("outside")));
        assertTrue(scope.allows(own,"inside"));assertFalse(scope.allows(own,"new"));
    }
    @Test void actualNonAirValidatorRejectsAirAndStructureVoid(){
        for(String cell:List.of("outside","air","structure_void"))
            assertThrows(IllegalArgumentException.class,()->scope.set(own,List.of(cell),"nonair"::equals));
        assertFalse(scope.active());
    }
    @Test void scopeMismatchFailsClosedAndCannotMutate(){
        scope.set(own,List.of("inside"),p->true);
        for(var foreign:List.of(new ProjectionBatchScope.Owner("other","task","world","projection"),
            new ProjectionBatchScope.Owner("lease","other","world","projection"),
            new ProjectionBatchScope.Owner("lease","task","other","projection"),
            new ProjectionBatchScope.Owner("lease","task","world","other"))){
            assertFalse(scope.current(foreign));assertFalse(scope.allows(foreign,"inside"));
            assertThrows(IllegalStateException.class,()->scope.clear(foreign));
            assertThrows(IllegalStateException.class,()->scope.set(foreign,List.of("portal"),p->true));
        }
        assertTrue(scope.allows(own,"inside"));assertFalse(scope.allows(null,"inside"));
    }
    @Test void lifecycleResetClearsOwnershipAndCoordinates(){scope.set(own,List.of("a"),p->true);scope.reset();assertFalse(scope.active());assertEquals(0,scope.count());assertNull(scope.owner());}
    @Test void maximumAndDuplicateCoordinatesAreChecked(){
        var points=new ArrayList<String>();for(int i=0;i<2048;i++)points.add("p"+i);
        scope.set(own,points,p->true);assertEquals(2048,scope.count());points.add("too-many");
        assertThrows(IllegalArgumentException.class,()->scope.set(own,points,p->true));
        assertThrows(IllegalArgumentException.class,()->scope.set(own,List.of("same","same"),p->true));assertEquals(2048,scope.count());
    }
    @Test void requestRequiresSupportedIdleCurrentUnexpiredOwner(){
        assertDoesNotThrow(()->ProjectionBatchScope.request(true,true,true,42,42,5000));
        for(long expiry:List.of(-1L,15001L))assertThrows(IllegalStateException.class,()->ProjectionBatchScope.request(true,true,true,42,42,expiry));
        assertThrows(IllegalStateException.class,()->ProjectionBatchScope.request(false,true,true,42,42,5000));
        assertThrows(IllegalStateException.class,()->ProjectionBatchScope.request(true,false,true,42,42,5000));
        assertThrows(IllegalStateException.class,()->ProjectionBatchScope.request(true,true,false,42,42,5000));
        assertThrows(IllegalStateException.class,()->ProjectionBatchScope.request(true,true,true,41,42,5000));
    }
    @Test void stableModelHashIncludesStateAndCoordinateButIgnoresEnumerationOrder(){
        String a="1,2,3\tBlock{minecraft:stone}\tminecraft:stone",b="4,5,6\tBlock{minecraft:iron_block}\tminecraft:iron_block";
        assertEquals(ProjectionAudit.contentHash(List.of(a,b)),ProjectionAudit.contentHash(List.of(b,a)));
        assertNotEquals(ProjectionAudit.contentHash(List.of(a,b)),ProjectionAudit.contentHash(List.of(a,b+"changed")));
        assertEquals(64,ProjectionAudit.contentHash(List.of(a)).length());
    }
    @Test void minimumFeetBoundsIncludeSmallTopMarginAndRejectInvalidValues(){
        assertEquals(64,ProjectionBatchScope.minimumFeet(64,64,186));assertEquals(189,ProjectionBatchScope.minimumFeet(189,64,186));
        for(double y:new double[]{63,190,64.5,Double.NaN,Double.POSITIVE_INFINITY})assertThrows(IllegalArgumentException.class,()->ProjectionBatchScope.minimumFeet(y,64,186));
    }
    @Test void feetRestrictionIsBatchLocalAndOnlyActorHasTolerance(){
        scope.set(own,List.of("ceiling"),p->true,87);
        assertFalse(scope.allowsStation(86));assertTrue(scope.allowsStation(87));
        assertFalse(scope.allowsFeet(86.89));assertTrue(scope.allowsFeet(86.9));assertTrue(scope.allowsFeet(100));assertFalse(scope.allowsFeet(Double.NaN));
        scope.clear(own);assertNull(scope.minFeetY());assertTrue(scope.allowsFeet(1));assertTrue(scope.allowsStation(1));
        scope.set(own,List.of("lower"),p->true);assertTrue(scope.allowsFeet(1));
    }
    @Test void failedReplacementRetainsPreviousFeetRestriction(){
        scope.set(own,List.of("ceiling"),p->true,87);
        assertThrows(IllegalArgumentException.class,()->scope.set(own,List.of("outside"),p->false,64));
        assertEquals(87,scope.minFeetY());assertFalse(scope.allowsFeet(86));
    }

}
