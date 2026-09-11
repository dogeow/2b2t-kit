package dev.twob2tkit.compat;

import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.AnnotationNode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** Verify optional target and cancellation wiring without launching a graphical Minecraft client. */
class MeteorGuardWiringTest {
	@Test void optionalMixinTargetsExactlyTheCrashingPreTickAndCancelsAtHead() throws Exception {
		ClassNode node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/mixin/MeteorKillAuraWorldGuardMixin.class")) {
			assertNotNull(in); new ClassReader(in).accept(node, 0);
		}
		List<AnnotationNode> annotations = new ArrayList<>();
		if (node.visibleAnnotations != null) annotations.addAll(node.visibleAnnotations);
		if (node.invisibleAnnotations != null) annotations.addAll(node.invisibleAnnotations);
		assertTrue(annotations.stream().anyMatch(a -> a.desc.endsWith("/Pseudo;")), "Meteor must remain optional");
		var mixin = annotations.stream().filter(a -> a.desc.endsWith("/Mixin;")).findFirst().orElseThrow();
		assertEquals(List.of("meteordevelopment.meteorclient.systems.modules.combat.KillAura"), value(mixin, "targets"));
		var method = node.methods.stream().filter(m -> m.name.equals("kit$skipTickWithoutWorld")).findFirst().orElseThrow();
		var inject = method.visibleAnnotations.stream().filter(a -> a.desc.endsWith("/Inject;")).findFirst().orElseThrow();
		assertEquals(List.of("onTick(Lmeteordevelopment/meteorclient/events/world/TickEvent$Pre;)V"), value(inject, "method"));
		assertEquals(true, value(inject, "cancellable"));
		assertEquals(false, value(inject, "remap"));
		assertEquals("HEAD", value((AnnotationNode)((List<?>)value(inject, "at")).getFirst(), "value"));
		var json = JsonParser.parseString(Files.readString(Path.of("src/client/resources/twob2tkit.client.mixins.json"))).getAsJsonObject();
		assertTrue(json.getAsJsonArray("client").asList().stream().anyMatch(e -> e.getAsString().equals("MeteorKillAuraWorldGuardMixin")));
	}
	private static Object value(AnnotationNode node, String key) {
		for (int i = 0; i < node.values.size(); i += 2) if (node.values.get(i).equals(key)) return node.values.get(i + 1);
		throw new AssertionError("Missing annotation value: " + key);
	}
}
