package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InterfacePausePolicyTest {
    @Test void passiveUiKeepsTheCurrentTaskWhileEveryInventoryControlIsExcluded(){
        assertTrue(InterfacePausePolicy.pauses(true,true,false,true,false));
        assertFalse(InterfacePausePolicy.pauses(true,true,true,true,false),"A user inventory screen is a container control, even with menu zero");
        assertFalse(InterfacePausePolicy.pauses(true,true,true,false,false),"Chest/crafting controls retain their ownership gate");
        assertFalse(InterfacePausePolicy.pauses(true,true,false,false,false),"A hidden foreign menu cannot gain ownership via chat");
    }
    @Test void safetyAndNormalWorkCannotBeMistakenForUiPause(){
        assertFalse(InterfacePausePolicy.pauses(false,true,false,true,false),"Death/disconnect retain cleanup priority");
        assertFalse(InterfacePausePolicy.pauses(true,false,false,true,false),"Closing the interface resumes the same operation");
        assertFalse(InterfacePausePolicy.pauses(true,true,false,true,true),"Verified underwater emergency ascent outranks the screen");
    }
    @Test void readOrStopNeverIncludesANewInventoryOrMovementAction(){
        for(String op:new String[]{"stop","safe_logout","material_job_pause","snapshot","scan","scan_trees"})
            assertTrue(InterfacePausePolicy.readOrStop(op));
        for(String op:new String[]{"slot_click","interact","select_item","craft_recipe","walk","navigate","mine_block","material_session","guard"})
            assertFalse(InterfacePausePolicy.readOrStop(op),op);
    }
}
