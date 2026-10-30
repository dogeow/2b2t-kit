package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class SourceColumnSupplyPolicyTest {
    @Test void onlyTheSupportedCompleteMiddleRowCanSupply(){
        assertTrue(SourceColumnSupplyPolicy.ready(true,0,0,0,true));
        assertFalse(SourceColumnSupplyPolicy.ready(false,0,0,0,true));
        assertFalse(SourceColumnSupplyPolicy.ready(true,0,0,0,false));
        for(int level:new int[]{-1,1,8,15}){
            assertFalse(SourceColumnSupplyPolicy.ready(true,level,0,0,true));
            assertFalse(SourceColumnSupplyPolicy.ready(true,0,level,0,true));
            assertFalse(SourceColumnSupplyPolicy.ready(true,0,0,level,true));
        }
    }
    @Test void otherWaterModesCannotBeMixedWithSupply(){
        assertTrue(SourceColumnSupplyPolicy.exclusiveFill(true,false,false,false,false));
        assertFalse(SourceColumnSupplyPolicy.exclusiveFill(false,false,false,false,false));
        for(int flags=1;flags<16;flags++)assertFalse(SourceColumnSupplyPolicy.exclusiveFill(true,(flags&1)!=0,(flags&2)!=0,(flags&4)!=0,(flags&8)!=0));
    }
    @Test void onlyTheLocalPlayerInAnExplicitSupplyFillGetsTheEntityException(){
        for(boolean fill:new boolean[]{false,true})for(boolean supply:new boolean[]{false,true})for(boolean local:new boolean[]{false,true})
            assertEquals(!(fill&&supply&&local),SourceColumnSupplyPolicy.entityBlocks(fill,supply,local));
    }
}
