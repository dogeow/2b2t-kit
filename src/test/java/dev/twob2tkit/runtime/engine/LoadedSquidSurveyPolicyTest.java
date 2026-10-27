package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoadedSquidSurveyPolicyTest {
    @Test void glowingTargetsRemainASeparateWildEntityObservation(){
        assertTrue(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,false,10,25));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,true,10,25));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",false,false,false,10,25));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,true,false,10,25));
        assertTrue(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,false,10,30));
        assertTrue(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,false,10,32));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,false,10,320));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:glow_squid",true,false,false,10,Double.NaN));
        assertFalse(LoadedSquidSurveyPolicy.glowTarget("minecraft:squid",true,false,false,10,25));
    }
    @Test void includesOnlyUserRequestedHeightAndOrdinaryWildSquid(){
        assertTrue(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,10,50));
        assertTrue(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,10,64));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,10,49.99));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,10,64.01));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:glow_squid",true,false,false,10,55));
    }
    @Test void neverSuppliesNamedDeadRemovedOrInvalidTargets(){
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,true,10,55));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",false,false,false,10,55));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,true,false,10,55));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,0,55));
        assertFalse(LoadedSquidSurveyPolicy.target("minecraft:squid",true,false,false,10,Double.NaN));
    }
}
