package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class CaptureTargetPolicyTest {
    @Test void explicit_preparation_can_span_one_minute_without_relaxing_health_or_expiry(){
        var h=owner();var s=new CaptureTargetPolicy.Scope("world","lease","task",7,"player",target,"minecraft:zombie",1000,61000);
        assertTrue(CaptureTargetPolicy.admit(s,h,1200));
        var later=new CaptureTargetPolicy.Owner("world","lease","task",7,"player",59000,true,true,true,false,false,20,false);
        assertTrue(CaptureTargetPolicy.owns(s,later,59000,false));assertFalse(CaptureTargetPolicy.owns(s,later,61001,false));
        var injured=new CaptureTargetPolicy.Owner("world","lease","task",7,"player",59000,true,true,true,false,false,19,false);
        assertFalse(CaptureTargetPolicy.owns(s,injured,59000,false));
        assertFalse(CaptureTargetPolicy.admit(new CaptureTargetPolicy.Scope("world","lease","task",7,"player",target,"minecraft:zombie",1000,61001),h,1200));
    }
    final UUID target=UUID.fromString("00000000-0000-0000-0000-000000000001");
    CaptureTargetPolicy.Scope scope(){return new CaptureTargetPolicy.Scope("world","lease","task",7,"player",target,"minecraft:zombie",1000,9000);}
    CaptureTargetPolicy.Owner owner(){return new CaptureTargetPolicy.Owner("world","lease","task",7,"player",1100,true,true,true,false,false,20,false);}
    @Test void unnamed_retention_requires_the_exact_live_ordinary_boat(){
        UUID boat=UUID.randomUUID();
        assertTrue(CaptureTargetPolicy.aboardExpectedBoat(boat,boat,true,true,true));
        assertFalse(CaptureTargetPolicy.aboardExpectedBoat(null,boat,true,true,true));
        assertFalse(CaptureTargetPolicy.aboardExpectedBoat(boat,UUID.randomUUID(),true,true,true));
        assertFalse(CaptureTargetPolicy.aboardExpectedBoat(boat,boat,false,true,true));
        assertFalse(CaptureTargetPolicy.aboardExpectedBoat(boat,boat,true,false,true));
        assertFalse(CaptureTargetPolicy.aboardExpectedBoat(boat,boat,true,true,false));
    }
    @Test void drowned_bait_keeps_exact_type_identity_and_all_owner_checks(){
        var s=scope();var drowned=new CaptureTargetPolicy.Scope(s.world(),s.lease(),s.task(),s.revision(),s.player(),s.target(),"minecraft:drowned",s.issued(),s.expires());
        assertTrue(CaptureTargetPolicy.admit(drowned,owner(),1200));
        assertTrue(CaptureTargetPolicy.subject(drowned,target,"minecraft:drowned",true,false,20,false,"Drowned",20));
        assertFalse(CaptureTargetPolicy.subject(drowned,target,"minecraft:zombie",true,false,20,false,"Zombie",20));
        assertFalse(CaptureTargetPolicy.subject(drowned,target,"minecraft:drowned",true,true,20,false,"Drowned",20));
        assertFalse(CaptureTargetPolicy.baitType("minecraft:villager"));
        var foreign=new CaptureTargetPolicy.Scope(s.world(),s.lease(),s.task(),s.revision(),s.player(),s.target(),"minecraft:villager",s.issued(),s.expires());
        assertFalse(CaptureTargetPolicy.admit(foreign,owner(),1200));
        assertFalse(CaptureTargetPolicy.subject(foreign,target,"minecraft:villager",true,false,20,false,"Villager",2));
    }
    @Test void current_healthy_single_target_is_admitted_but_never_an_attack_permission(){
        assertTrue(CaptureTargetPolicy.admit(scope(),owner(),1200));
        assertTrue(CaptureTargetPolicy.subject(scope(),target,"minecraft:zombie",true,false,20,false,"Zombie",20));
        assertTrue(CaptureTargetPolicy.veto(target,target,true,true,true));
        assertFalse(CaptureTargetPolicy.veto(target,UUID.randomUUID(),true,true,true));
        assertFalse(CaptureTargetPolicy.veto(target,target,false,true,true));
        assertFalse(CaptureTargetPolicy.veto(target,target,true,false,true));
    }
    @Test void different_scope_manual_control_hold_stale_status_and_injury_refuse_capture(){
        var h=owner();
        for(var bad: new CaptureTargetPolicy.Owner[]{
            new CaptureTargetPolicy.Owner("other",h.lease(),h.task(),7,h.player(),1100,true,true,true,false,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),"other",h.task(),7,h.player(),1100,true,true,true,false,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),"other",7,h.player(),1100,true,true,true,false,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),8,h.player(),1100,true,true,true,false,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,"other",1100,true,true,true,false,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,h.player(),1100,true,true,true,true,false,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,h.player(),1100,true,true,true,false,true,20,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,h.player(),1100,true,true,true,false,false,19,false),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,h.player(),1100,true,true,true,false,false,20,true),
            new CaptureTargetPolicy.Owner(h.world(),h.lease(),h.task(),7,h.player(),1100,true,false,true,false,false,20,false)
        }) assertFalse(CaptureTargetPolicy.admit(scope(),bad,1200),bad.toString());
        assertFalse(CaptureTargetPolicy.admit(scope(),h,3000));
        assertFalse(CaptureTargetPolicy.admit(scope(),h,9500));
    }
    @Test void villager_baby_dead_foreign_named_or_wrong_identity_is_never_excluded(){
        assertFalse(CaptureTargetPolicy.subject(scope(),target,"minecraft:villager",true,false,20,false,"Villager",2));
        assertFalse(CaptureTargetPolicy.subject(scope(),target,"minecraft:zombie",true,true,20,false,"Zombie",2));
        assertFalse(CaptureTargetPolicy.subject(scope(),target,"minecraft:zombie",false,false,0,false,"Zombie",2));
        assertFalse(CaptureTargetPolicy.subject(scope(),UUID.randomUUID(),"minecraft:zombie",true,false,20,false,"Zombie",2));
        assertFalse(CaptureTargetPolicy.subject(scope(),target,"minecraft:zombie",true,false,20,true,"Someone else's mob",2));
        assertTrue(CaptureTargetPolicy.subject(scope(),target,"minecraft:zombie",true,false,20,true,CaptureTargetPolicy.NAME,2));
    }
    @Test void named_target_remains_protected_after_arming_timeout_only_for_the_same_live_owner(){
        var h=new CaptureTargetPolicy.Owner("world","lease","task",7,"player",11000,true,true,true,false,false,18,false);
        assertTrue(CaptureTargetPolicy.owns(scope(),h,11000,true));
        assertFalse(CaptureTargetPolicy.owns(scope(),h,11000,false));
    }
    @Test void same_lease_native_inputs_keep_protection_but_cannot_admit_a_stale_request(){
        var next=new CaptureTargetPolicy.Owner("world","lease","task",8,"player",1200,true,true,true,false,false,20,false);
        assertTrue(CaptureTargetPolicy.owns(scope(),next,1200,false));
        assertFalse(CaptureTargetPolicy.admit(scope(),next,1200));
        var rollback=new CaptureTargetPolicy.Owner("world","lease","task",6,"player",1200,true,true,true,false,false,20,false);
        assertFalse(CaptureTargetPolicy.owns(scope(),rollback,1200,true));
        var manual=new CaptureTargetPolicy.Owner("world","lease","task",8,"player",1200,true,true,true,true,false,20,false);
        assertFalse(CaptureTargetPolicy.owns(scope(),manual,1200,true));
        var replaced=new CaptureTargetPolicy.Owner("world","replacement","task",8,"player",1200,true,true,true,false,false,20,false);
        assertFalse(CaptureTargetPolicy.owns(scope(),replaced,1200,true));
    }
}
