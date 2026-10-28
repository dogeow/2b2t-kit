package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.EnumMap;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.automation.BelowFlowMiningPolicy.*;

class BelowFlowMiningPolicyTest {
    @Test void sourceBelowNeedsExplicitPreservationAndExactPinnedState(){
        var rows=neighbors();rows.put(Side.DOWN,Fluid.WATER_SOURCE);
        assertNotNull(rejection(true,true,true,true,false,true,rows));
        assertNull(rejection(true,true,true,true,false,true,true,rows));
        assertNotNull(rejection(true,true,true,true,false,false,true,rows));
    }
    @Test void preservationScopeDoesNotAdmitOtherLiquidsOrOtherSources(){
        var rows=neighbors();rows.put(Side.DOWN,Fluid.OTHER);
        assertNotNull(rejection(true,true,true,true,false,true,true,rows));
        rows=neighbors();rows.put(Side.DOWN,Fluid.WATER_SOURCE);rows.put(Side.EAST,Fluid.WATER_SOURCE);
        assertNotNull(rejection(true,true,true,true,false,true,true,rows));
        rows.put(Side.EAST,Fluid.DRY);
        assertNotNull(rejection(true,true,true,true,true,true,true,rows));
    }
    private EnumMap<Side,Fluid> neighbors(){
        var rows=new EnumMap<Side,Fluid>(Side.class);
        for(var side:Side.values())rows.put(side,Fluid.DRY);
        rows.put(Side.DOWN,Fluid.FLOWING_WATER);return rows;
    }
    @Test void admitsOnlyVerifiedDryGlassAboveFlow(){
        assertNull(rejection(true,true,true,true,false,true,neighbors()));
    }
    @Test void sourcesLavaAndMissingWaterBelowStayProtected(){
        for(var fluid:new Fluid[]{Fluid.WATER_SOURCE,Fluid.OTHER,Fluid.DRY,Fluid.UNKNOWN}){
            var rows=neighbors();rows.put(Side.DOWN,fluid);
            assertNotNull(rejection(true,true,true,true,false,true,rows));
        }
    }
    @Test void fluidAtEveryOtherFaceIsRejected(){
        for(var side:Side.values())if(side!=Side.DOWN){
            var rows=neighbors();rows.put(side,Fluid.FLOWING_WATER);
            assertNotNull(rejection(true,true,true,true,false,true,rows));
        }
    }
    @Test void staleScopeHealthProjectionToolAndFootingAreRejected(){
        assertNotNull(rejection(false,true,true,true,false,true,neighbors()));
        assertNotNull(rejection(true,false,true,true,false,true,neighbors()));
        assertNotNull(rejection(true,true,false,true,false,true,neighbors()));
        assertNotNull(rejection(true,true,true,false,false,true,neighbors()));
        assertNotNull(rejection(true,true,true,true,true,true,neighbors()));
        assertNotNull(rejection(true,true,true,true,false,false,neighbors()));
    }
    @Test void partialObservationsCannotAuthorizeAnAction(){
        var rows=neighbors();rows.remove(Side.NORTH);
        assertNotNull(rejection(true,true,true,true,false,true,rows));
        rows=neighbors();rows.put(Side.NORTH,null);
        assertNotNull(rejection(true,true,true,true,false,true,rows));
    }
}
