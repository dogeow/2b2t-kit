package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ChannelWaterPlacementPolicyTest {
 @Test void bothSourceRowsNeedACompleteShortChannel(){assertTrue(ChannelWaterPlacementPolicy.shape(8,2,0));assertTrue(ChannelWaterPlacementPolicy.shape(8,2,1));assertTrue(ChannelWaterPlacementPolicy.geometry(8,2,14,2,18,2));}
 @Test void aMissingFloorSideHopperOrOutletNeverPermitsWater(){for(int i=0;i<4;i++){int[] n={14,2,18,2};n[i]--;assertFalse(ChannelWaterPlacementPolicy.geometry(8,2,n[0],n[1],n[2],n[3]));}}
 @Test void rejectUnboundedWidthsRowsAndWaterTravelBeyondSevenBlocks(){assertFalse(ChannelWaterPlacementPolicy.shape(9,2,0));assertFalse(ChannelWaterPlacementPolicy.shape(8,3,0));assertFalse(ChannelWaterPlacementPolicy.shape(8,2,2));assertFalse(ChannelWaterPlacementPolicy.shape(1,2,0));}
}
