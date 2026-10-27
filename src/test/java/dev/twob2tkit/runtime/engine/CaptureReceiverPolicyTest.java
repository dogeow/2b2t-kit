package dev.twob2tkit.runtime.engine;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CaptureReceiverPolicyTest {
    @Test void an_explicit_unleashed_receiver_does_not_take_a_foreign_leash_or_authorize_cargo(){
        assertFalse(CaptureReceiverPolicy.receiverBoat(true,true,true,false,false,false));
        assertTrue(CaptureReceiverPolicy.receiverBoat(true,true,true,false,false,true));
        assertTrue(CaptureReceiverPolicy.receiverBoat(true,true,true,true,true,false));
        assertFalse(CaptureReceiverPolicy.receiverBoat(true,true,true,true,false,true));
        assertFalse(CaptureReceiverPolicy.receiverBoat(true,true,false,false,false,true));
        assertFalse(CaptureReceiverPolicy.receiverBoat(false,true,true,false,false,true));
        assertFalse(CaptureReceiverPolicy.receiverBoat(true,false,true,false,false,true));
    }
    @Test void a_consumed_receiver_stays_consumed_after_manual_capture_and_runtime_reload(){
        assertTrue(CaptureReceiverPolicy.claimed("one","one","",false));
        assertTrue(CaptureReceiverPolicy.claimed("one","","rx-one-target",false));
        assertTrue(CaptureReceiverPolicy.claimed("one","","new-manual-target",true));
        assertFalse(CaptureReceiverPolicy.claimed("two","one","rx-one-target",false));
        assertFalse(CaptureReceiverPolicy.claimed("","","",false));
    }
    final UUID boat=UUID.randomUUID();
    CaptureReceiverPolicy.Request request(){return new CaptureReceiverPolicy.Request("receiver1","w","lease","task",7,"player",boat,1000,601000);}
    CaptureTargetPolicy.Owner owner(boolean busy){return new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,true,true,true,false,false,20,busy);}
    @Test void explicitly_prepared_receiver_can_claim_bait_before_automatic_combat(){
        assertTrue(CaptureReceiverPolicy.authorized(request(),owner(false),1200));
        assertTrue(CaptureReceiverPolicy.authorized(request(),owner(true),1200));
        assertFalse(CaptureTargetPolicy.admit(new CaptureTargetPolicy.Scope("w","lease","task",8,"player",boat,"minecraft:zombie",1000,16000),owner(true),1200));
    }
    @Test void receiver_keeps_world_owner_manual_health_and_bounded_time_checks(){
        var r=request();var h=owner(false);
        for(var bad:new CaptureReceiverPolicy.Request[]{
            new CaptureReceiverPolicy.Request("receiver1","other",r.lease(),r.task(),7,r.player(),boat,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),"other",r.task(),7,r.player(),boat,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),r.lease(),"other",7,r.player(),boat,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),r.lease(),r.task(),9,r.player(),boat,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),r.lease(),r.task(),7,"other",boat,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),r.lease(),r.task(),7,r.player(),null,1000,601000),
            new CaptureReceiverPolicy.Request("receiver1",r.world(),r.lease(),r.task(),7,r.player(),boat,1000,601001)
        })assertFalse(CaptureReceiverPolicy.authorized(bad,h,1200));
        assertFalse(CaptureReceiverPolicy.authorized(r,h,999));assertFalse(CaptureReceiverPolicy.authorized(r,h,601000));
        for(var bad:new CaptureTargetPolicy.Owner[]{
            new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,true,true,true,true,false,20,false),
            new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,true,true,true,false,true,20,false),
            new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,true,true,true,false,false,19,false),
            new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,true,false,true,false,false,20,false),
            new CaptureTargetPolicy.Owner("w","lease","task",8,"player",1100,false,true,true,false,false,20,false)
        })assertFalse(CaptureReceiverPolicy.authorized(r,bad,1200));
        assertFalse(CaptureReceiverPolicy.authorized(r,h,3000));
    }
    @Test void only_reachable_full_health_unowned_adult_bait_is_selected(){
        assertTrue(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,false,20,"minecraft:air",18,40,-4));
        assertTrue(CaptureReceiverPolicy.candidate("minecraft:drowned",true,false,false,false,false,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:drowned",true,false,false,false,false,20,"minecraft:trident",5,6,0));
        for(String type:new String[]{"minecraft:villager","minecraft:zombie_villager","minecraft:creeper"})
            assertFalse(CaptureReceiverPolicy.candidate(type,true,false,false,false,false,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,true,false,false,false,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,true,false,false,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,true,false,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,true,20,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,false,19,"minecraft:air",5,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,false,20,"minecraft:air",19,6,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,false,20,"minecraft:air",5,65,0));
        assertFalse(CaptureReceiverPolicy.candidate("minecraft:zombie",true,false,false,false,false,20,"minecraft:air",5,6,-5));
    }
}
