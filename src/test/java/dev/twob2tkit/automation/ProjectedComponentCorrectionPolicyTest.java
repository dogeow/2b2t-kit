package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.automation.ProjectedComponentCorrectionPolicy.*;

class ProjectedComponentCorrectionPolicyTest {
    private String state(String face,boolean powered){return "Block{minecraft:observer}[facing="+face+",powered="+powered+"]";}
    @Test void allSixDirectionalMistakesCanBeCorrected(){
        for(String actual:new String[]{"down","up","north","south","west","east"})
            for(String goal:new String[]{"down","up","north","south","west","east"})
                assertEquals(!actual.equals(goal),observerCorrection(state(actual,false),state(goal,true)));
    }
    @Test void pulseStateAloneNeverAuthorizesRemovingCorrectObservers(){
        assertFalse(observerCorrection(state("south",false),state("south",true)));
        assertFalse(observerCorrection(state("south",true),state("south",false)));
    }
    @Test void blockEntitiesLiquidsNaturalAndDifferentMaterialsNeverQualify(){
        for(String unsafe:new String[]{"Block{minecraft:dropper}[facing=north,triggered=false]",
                "Block{minecraft:hopper}[enabled=true,facing=south]","Block{minecraft:chest}",
                "Block{minecraft:water}[level=0]","Block{minecraft:dirt}","Block{minecraft:air}",
                "Block{minecraft:magma_block}","Block{minecraft:piston}[extended=false,facing=north]"}){
            assertFalse(observerCorrection(unsafe,state("south",false)));
            assertFalse(observerCorrection(state("north",false),unsafe));
        }
    }
    @Test void malformedOrAdditionalPropertiesCannotWidenTheMode(){
        for(String unsafe:new String[]{"",state("invalid",false),"Block{minecraft:observer}[facing=north]",
                "Block{minecraft:observer}[facing=north,powered=false,waterlogged=true]",
                "Block{minecraft:observer}[facing=north,powered=0]"})
            assertFalse(observerCorrection(unsafe,state("south",false)));
        assertFalse(observerCorrection(null,state("south",false)));
        assertFalse(observerCorrection(state("north",false),null));
    }
}
