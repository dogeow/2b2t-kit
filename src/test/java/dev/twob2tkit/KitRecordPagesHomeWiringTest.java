package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

import java.util.ArrayList;

import static org.junit.jupiter.api.Assertions.*;

class KitRecordPagesHomeWiringTest {
	@Test void primaryPlacesPageShowsAndSetsTheUniqueHome() throws Exception {
		var node=new ClassNode();
		try(var input=getClass().getResourceAsStream("/dev/twob2tkit/KitRecordPages.class")){
			assertNotNull(input);new ClassReader(input).accept(node,0);
		}
		var places=node.methods.stream().filter(method->method.name.equals("places"))
			.findFirst().orElseThrow();
		var constants=new ArrayList<String>();var calls=new ArrayList<MethodInsnNode>();
		for(var instruction:places.instructions){
			if(instruction instanceof LdcInsnNode value&&value.cst instanceof String text)constants.add(text);
			if(instruction instanceof MethodInsnNode call)calls.add(call);
		}
		assertTrue(constants.contains("设家"));
		assertTrue(node.methods.stream().filter(method->method.name.contains("lambda$places"))
			.flatMap(method->{
				var found=new ArrayList<MethodInsnNode>();
				for(var instruction:method.instructions)
					if(instruction instanceof MethodInsnNode call)found.add(call);
				return found.stream();
			}).anyMatch(call->call.owner.endsWith("/KitConfig")
				&&call.name.equals("setHomePlace")));
	}
}
