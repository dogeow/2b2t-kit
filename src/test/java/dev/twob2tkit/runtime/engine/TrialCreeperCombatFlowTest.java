package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class TrialCreeperCombatFlowTest {
    @Test void observedNoBowTimeoutAllowsOneVerifiedModeChangeWithoutInventingADeath(){
        UUID id=UUID.randomUUID();var session=new BorerCombatSession<String>();
        session.beginTick(0);session.observe(id,"live 20 hp creeper",true,false,true,20);
        session.beginTick(600);session.observe(id,"same live creeper",true,false,true,20);
        assertFalse(session.canAttack(id));assertTrue(session.canRetryTrialMelee(id));
        assertFalse(session.retryTrialMelee(id,false));
        assertTrue(session.retryTrialMelee(id,true));assertTrue(session.canAttack(id));assertTrue(session.contains(id));
        var cycle=new TrialCreeperFlightPolicy();
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,
            cycle.step(id,600,1,-73,20,8,63,66,false,false,false,true,true).decision());
        cycle.attacked();
        assertEquals("no_confirmed_damage",cycle.step(id,840,1,-73,20,8,74,66,true,false,false,true,true).reason());
        session.beginTick(1200);session.observe(id,"still live",true,false,true,20);
        assertFalse(session.retryTrialMelee(id,true));assertFalse(session.canAttack(id));assertTrue(session.pending());
    }
    @Test void missingObservationsCannotEarnTheModeRetryAndOnlyHealthOrDeathHasMeaning(){
        UUID id=UUID.randomUUID();var session=new BorerCombatSession<String>();
        session.beginTick(0);session.observe(id,"20 hp",true,false,true,20);session.beginTick(700);
        assertFalse(session.canRetryTrialMelee(id));assertFalse(session.retryTrialMelee(id,true));assertTrue(session.pending());
        session.observe(id,"live returned",false,false,true,20);assertTrue(session.retryTrialMelee(id,true));
        session.beginTick(1299);session.observe(id,"damage confirmed",false,false,true,16);
        session.beginTick(1300);session.observe(id,"same health",false,false,true,16);assertTrue(session.canAttack(id));
        session.observe(id,"unloaded",false,false,false,16);assertTrue(session.contains(id));
        session.observe(id,"confirmed dead",false,true,false,0);assertFalse(session.pending());
    }
    @Test void explicitHostOptInRunsBeforeOldEvasionAndFlightUsesCheckedNormalInputs()throws Exception{
        var tick=calls(method("runtime/engine/BorerRangedCombat","tick"));
        assertTrue(tick.indexOf("trialCreeperFlight")<tick.indexOf("evadeCreeper"));
        assertTrue(tick.indexOf("trialCreeperFlight")<tick.indexOf("safetyRise"));
        var actor=method("runtime/engine/BorerRangedCombat","trialCreeperFlight");var linked=calls(actor);
        assertTrue(linked.containsAll(List.of("allowTrialCreeperMelee","retryTrialMelee","isWithinAttackRange",
            "getAttackStrengthScale","trialFlightColumn","attack","swing","trialFlightMove")));
        assertTrue(actor.tryCatchBlocks.stream().anyMatch(t->"java/lang/LinkageError".equals(t.type)));
        assertFalse(linked.contains("clear"));assertFalse(linked.contains("enablePveMelee"));
        var fallback=method("runtime/api/BorerHost","allowTrialCreeperMelee");
        var operations=new ArrayList<Integer>();for(var instruction:fallback.instructions)
            if(instruction.getOpcode()>=0)operations.add(instruction.getOpcode());
        assertEquals(List.of(Opcodes.ICONST_0,Opcodes.IRETURN),operations);
        for(var instruction:actor.instructions)if(instruction instanceof MethodInsnNode call)
            assertFalse(call.owner.startsWith("dev/twob2tkit/")&&!call.owner.startsWith("dev/twob2tkit/runtime/"),
                "Engine must not depend on host implementation: "+call.owner);
    }
    @Test void anActualObstructingCeilingRequiresARealBoundedDetourAndClosedWorldHasNoFakeRoute(){
        var start=new net.minecraft.core.BlockPos(0,0,0);var high=new net.minecraft.core.BlockPos(-7,11,3);
        var detour=BorerFlyPath.findExact(q->!(q.getY()==2&&Math.abs(q.getX())<=1&&Math.abs(q.getZ())<=1),start,high,12,1600);
        assertFalse(detour.nodes().isEmpty());
        for(var q:detour.nodes())assertFalse(q.getY()==2&&Math.abs(q.getX())<=1&&Math.abs(q.getZ())<=1);
        for(int i=1;i<detour.nodes().size();i++)assertEquals(1,detour.nodes().get(i).distManhattan(detour.nodes().get(i-1)));
        var blocked=BorerFlyPath.findExact(q->q.getY()<2,start,high,12,1600);
        assertTrue(blocked.nodes().isEmpty());assertTrue(blocked.expanded()<=1600);
    }
    @Test void horizontalDeferralRechecksLoadedTargetsAndGroundingBeforeReleasingWork()throws Exception{
        var tick=calls(method("runtime/engine/BorerRangedCombat","tick"));
        assertTrue(tick.indexOf("trialCreeperHorizontalDeferred")<tick.indexOf("safeVerticalSeparation"));
        assertTrue(tick.indexOf("trialCreeperHorizontalDeferred")<tick.indexOf("trialCreeperFlight"));
        var proof=calls(method("runtime/engine/BorerRangedCombat","trialCreeperHorizontalDeferred"));
        assertTrue(proof.containsAll(List.of("allowTrialCreeperMelee","onGround","noCollision","currentServerChunk","safe")));
        assertFalse(proof.contains("clear"));assertFalse(proof.contains("attack"));assertFalse(proof.contains("swing"));
        assertTrue(tick.contains("pause"),"Deferral pauses the same unresolved session rather than inventing a kill");
    }
    private MethodNode method(String path,String name)throws Exception{
        var node=new ClassNode();try(var input=getClass().getResourceAsStream("/dev/twob2tkit/"+path+".class")){
            assertNotNull(input);new ClassReader(input).accept(node,0);
        }return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode m){
        var result=new ArrayList<String>();for(var instruction:m.instructions)if(instruction instanceof MethodInsnNode call)result.add(call.name);
        return result;
    }
}
