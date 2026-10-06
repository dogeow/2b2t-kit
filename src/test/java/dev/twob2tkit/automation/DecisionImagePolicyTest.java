package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class DecisionImagePolicyTest {
    @Test void framebufferFitsSmallModelImageBudget(){
        for(int[] size:new int[][]{{1708,1024},{1636,1016},{1637,1019},{3840,2160},{640,360},{1,1}}){
            var bounded=DecisionImagePolicy.boundedSize(size[0],size[1]);
            assertTrue(bounded.width()>=1&&bounded.width()<=640&&bounded.height()>=1&&bounded.height()<=360);
            if(size[0]>640||size[1]>360)assertTrue(bounded.width()>=639||bounded.height()>=359);
        }
        assertThrows(IllegalArgumentException.class,()->DecisionImagePolicy.boundedSize(0,100));
    }
    @Test void pathAndWorldChangesCannotBecomeImages(){
        assertTrue(DecisionImagePolicy.validId("materials-1234"));
        assertFalse(DecisionImagePolicy.validId("../../secrets"));
        assertFalse(DecisionImagePolicy.validId("native.png"));
        assertTrue(DecisionImagePolicy.scope(true,true,true,1,1,.3));
        assertFalse(DecisionImagePolicy.scope(false,true,true,1,1,.3));
        assertFalse(DecisionImagePolicy.scope(true,true,false,1,1,.3));
        assertFalse(DecisionImagePolicy.scope(true,true,true,1,2,.3));
        assertFalse(DecisionImagePolicy.scope(true,true,true,1,1,Double.NaN));
    }
}
