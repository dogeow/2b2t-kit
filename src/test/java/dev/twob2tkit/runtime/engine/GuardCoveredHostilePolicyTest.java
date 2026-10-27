package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardCoveredHostilePolicyTest {
    @Test void recordedUnderFoundationCreeperDoesNotRequireAnUnrelatedRise(){
        assertTrue(GuardCoveredHostilePolicy.safe(new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,true,62.7,63,63.9375,64.15)));
        assertTrue(GuardCoveredHostilePolicy.safe(new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,true,62.7,63,63.9375,63.9375)));
        assertTrue(GuardCoveredHostilePolicy.safe(new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,true,62.7,63,64,79.2)));
    }
    @Test void drownedBehindRecordedRiverbedHasARealPhysicalBarrier(){
        assertTrue(GuardCoveredHostilePolicy.supported("minecraft:drowned"));
        assertTrue(GuardCoveredHostilePolicy.safe(new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,true,55.95,57,58,83.25)));
    }
    @Test void teleportsPhasingAndSonicAttacksNeverUseThisBarrierException(){
        for(String type:new String[]{"minecraft:enderman","minecraft:vex","minecraft:warden","minecraft:evoker","minecraft:ghast","minecraft:blaze","minecraft:wither","unknown"})
            assertFalse(GuardCoveredHostilePolicy.supported(type),type);
        for(String type:new String[]{"minecraft:skeleton","minecraft:stray","minecraft:bogged","minecraft:zombie","minecraft:husk","minecraft:spider","minecraft:cave_spider"})
            assertTrue(GuardCoveredHostilePolicy.supported(type),type);
    }
    @Test void actualExposurePowerSwellHitOrMissingFloorNeverDefersDefense(){
        var cases=new GuardCoveredHostilePolicy.Evidence[]{
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,true,false,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,false,false,false,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,true,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,true,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,false,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,false,false,true,true,false,false,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,true,true,true,false,false,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,false,true,false,false,false,true,62.7,63,64,64.15),
            new GuardCoveredHostilePolicy.Evidence(true,true,false,true,true,false,false,false,true,64.7,63,64,64.15)};
        for(var e:cases)assertFalse(GuardCoveredHostilePolicy.safe(e),e.toString());
    }
    @Test void fullWidthFarmlandAndSlabsCoverButFencesAndThinTrapdoorsDoNot(){
        assertTrue(GuardCoveredHostilePolicy.fullBarrierBox(0,0,0,1,.9375,1));
        assertTrue(GuardCoveredHostilePolicy.fullBarrierBox(0,.5,0,1,1,1));
        assertFalse(GuardCoveredHostilePolicy.fullBarrierBox(.375,0,.375,.625,1.5,.625));
        assertFalse(GuardCoveredHostilePolicy.fullBarrierBox(0,0,0,1,.1875,1));
        assertFalse(GuardCoveredHostilePolicy.fullBarrierBox(0,0,0,Double.NaN,1,1));
    }
}
