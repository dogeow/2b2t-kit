package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;

import static org.junit.jupiter.api.Assertions.*;

class SnowGuardScopePolicyTest {
	@Test void onlyExactCurrentSnowMaterialCruiseMayMoveTheGuardSite(){
		assertTrue(SnowGuardScopePolicy.rebase(true,true,true,true,true,true,true));
		for(int missing=0;missing<7;missing++){
			boolean[] values={true,true,true,true,true,true,true};values[missing]=false;
			assertFalse(SnowGuardScopePolicy.rebase(values[0],values[1],values[2],values[3],values[4],values[5],values[6]));
		}
	}

	@Test void ordinaryGuardKeepsTheExistingFiveHundredTwelveBlockBoundary(){
		assertTrue(AutomationScope.nearSite(511,0));
		assertFalse(AutomationScope.nearSite(513,0));
		assertFalse(SnowGuardScopePolicy.rebase(true,true,false,true,true,true,true));
		assertFalse(SnowGuardScopePolicy.rebase(true,true,true,true,false,true,true));
	}
	@Test void pendingReturnAndInflightScopesHaveDifferentAdmissionRequirements(){
		assertTrue(SnowGuardScopePolicy.pendingReturn(true,true,true,true,true));
		assertFalse(SnowGuardScopePolicy.pendingReturn(false,true,true,true,true));
		assertTrue(SnowGuardScopePolicy.inFlight(true,true,true,true,true,true));
		assertFalse(SnowGuardScopePolicy.inFlight(false,true,true,true,true,true));
		assertFalse(SnowGuardScopePolicy.inFlight(true,true,true,false,true,true));
	}

	@Test void liveRebaseAndGuardValidationShareOneFailClosedTryBlock()throws Exception{
		var node=new ClassNode();
		try(var input=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
			assertNotNull(input);new ClassReader(input).accept(node,0);
		}
		var method=node.methods.stream().filter(value->value.name.equals("beforeGuard"))
			.findFirst().orElseThrow();
		int snow=-1,parking=-1,guard=-1,index=0;
		for(var instruction:method.instructions){
			if(instruction instanceof MethodInsnNode call){
				if(call.name.equals("rebaseSnowExpeditionGuard"))snow=index;
				if(call.name.equals("rebaseParkingGuard"))parking=index;
				if(call.name.equals("guard"))guard=index;
			}index++;
		}
		assertTrue(parking>=0&&guard>parking&&snow>guard);
		final int first=parking,last=snow;
		assertTrue(method.tryCatchBlocks.stream().anyMatch(block->{
			int start=method.instructions.indexOf(block.start),end=method.instructions.indexOf(block.end);
			return start<=first&&last<end;
		}));
		var guardMethod=node.methods.stream().filter(value->value.name.equals("guard"))
			.findFirst().orElseThrow();
		assertTrue(calls(guardMethod,"activeSnowNavigationScope"));
		var tick=node.methods.stream().filter(value->value.name.equals("tick"))
			.findFirst().orElseThrow();
		assertTrue(calls(tick,"abortOwnedRequest"),
			"a revoked guard/lease must stop the active cruise and settle its permit");
	}
	private boolean calls(org.objectweb.asm.tree.MethodNode method,String name){
		for(var instruction:method.instructions)
			if(instruction instanceof MethodInsnNode call&&call.name.equals(name))return true;
		return false;
	}
}
