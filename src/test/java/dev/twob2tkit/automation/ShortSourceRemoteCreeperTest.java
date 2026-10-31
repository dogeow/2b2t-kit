package dev.twob2tkit.automation;
import net.minecraft.world.phys.AABB;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ShortSourceRemoteCreeperTest {
    private static SourceColumnThreatPolicy.Workspace valid(){return new SourceColumnThreatPolicy.Workspace(true,true,true,true,true,true);}
    @Test void recordedUnseenCalmCreepersAreOutsidePlayerAndEveryPartOfTheProtectedProfile(){
        var b=new ProjectedSourceColumnPolicy.Bounds(28,59,86,30,62,86);
        var player=new AABB(29.1666,60.075,86.2,29.7666,61.875,86.8);
        for(var enemy:new AABB[]{new AABB(17.8428,56,84.5586,18.4428,57.7,85.1586),new AABB(14.9031,56,86.5269,15.5031,57.7,87.1269),new AABB(22.9065,56,100.8504,23.5065,57.7,101.4504)}){
            double p=ProjectedSourceColumnGuard.boxDistanceSquared(player,enemy),s=ProjectedSourceColumnGuard.shortProtectedDistanceSquared(enemy,b);
            assertTrue(p>64);assertTrue(s>49);assertTrue(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,true,p,s));
        }
    }
    @Test void aFarPlayerDoesNotExcuseACreeperNearTheMachineOrOverflow(){
        var b=new ProjectedSourceColumnPolicy.Bounds(28,59,86,30,62,86);
        double near=ProjectedSourceColumnGuard.shortProtectedDistanceSquared(new AABB(28.2,56,86.2,28.8,57.7,86.8),b);
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,true,400,near));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,true,400,49));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,true,64,100));
    }
    @Test void poweredVisibleSwellingAboveFloorAndStaleCreaturesAreNeverIgnored(){
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),false,true,false,false,true,200,100));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,false,false,false,true,200,100));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,true,false,true,200,100));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,true,true,200,100));
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,false,200,100));
    }
    @Test void everyGeometryQuietAndProjectileProofIsStillRequired(){
        for(int i=0;i<5;i++){
            var w=new SourceColumnThreatPolicy.Workspace(i!=0,i!=1,i!=2,false,i!=3,i!=4);
            assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,w,true,true,false,false,true,200,100));
        }
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(true,valid(),true,true,false,false,true,Double.NaN,100));
    }
    @Test void oldNineRowPolicyAndItsSixteenBlockBoundaryRemainUnchanged(){
        assertFalse(SourceColumnThreatPolicy.shortRemoteCreeper(false,valid(),true,true,false,false,true,200,100));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,200));
        assertTrue(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,300));
    }
}
