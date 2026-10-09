package dev.twob2tkit.runtime.engine;
import java.util.UUID;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardShieldCycleTest {
    private final UUID archer=UUID.randomUUID();
    @Test void startsWithShieldAndDoesNotUseAScheduledUseKeyAsBlockingProof(){
        var c=new GuardShieldCycle();
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,0,true,false,0,false,false));
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,100,true,false,0,false,false));
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,101,true,true,0,false,false));
        assertEquals(GuardShieldCycle.Action.ATTACK,c.update(archer,109,true,true,0,false,false));
    }
    @Test void observedShieldWearAllowsOneCounterattackOnlyAfterBlockingSettles(){
        var c=new GuardShieldCycle();c.update(archer,0,true,true,0,false,false);
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,5,true,true,4,false,false));
        assertEquals(GuardShieldCycle.Action.ATTACK,c.update(archer,8,true,true,4,false,false));
        c.shot(9);
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,10,true,true,4,false,false));
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,18,true,true,4,false,false));
    }
    @Test void incomingArrowOrNewHurtCancelsAttackAndReblocks(){
        for(boolean hurt:new boolean[]{false,true}){
            var c=new GuardShieldCycle();c.update(archer,0,true,true,0,false,false);
            assertEquals(GuardShieldCycle.Action.ATTACK,c.update(archer,40,true,true,0,false,false));
            assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,41,true,false,0,!hurt,hurt));
        }
    }
    @Test void staleTargetSwitchDisableAndAttackBudgetCannotRetainCounterattack(){
        var c=new GuardShieldCycle();c.update(archer,0,true,true,0,false,false);
        c.update(archer,40,true,true,0,false,false);
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(archer,72,true,false,0,false,false));
        assertEquals(GuardShieldCycle.Action.BLOCK,c.update(UUID.randomUUID(),73,true,true,0,false,false));
        assertEquals(GuardShieldCycle.Action.DISABLED,c.update(archer,74,false,true,0,false,false));
        assertFalse(c.enabled());
    }
    @Test void predictiveArrowCheckRejectsOwnDirectionRecedingStationaryAndSideMisses(){
        var body=new AABB(-.3,0,-.3,.3,1.8,.3);
        assertTrue(GuardShieldCycle.incoming(new Vec3(8,.9,0),new Vec3(-1,0,0),body,Vec3.ZERO));
        assertFalse(GuardShieldCycle.incoming(new Vec3(8,.9,0),new Vec3(1,0,0),body,Vec3.ZERO));
        assertFalse(GuardShieldCycle.incoming(new Vec3(8,.9,3),new Vec3(-1,0,0),body,Vec3.ZERO));
        assertFalse(GuardShieldCycle.incoming(new Vec3(8,.9,0),Vec3.ZERO,body,Vec3.ZERO));
        assertTrue(GuardShieldCycle.incoming(new Vec3(Double.NaN,0,0),Vec3.ZERO,body,Vec3.ZERO));
    }
}
