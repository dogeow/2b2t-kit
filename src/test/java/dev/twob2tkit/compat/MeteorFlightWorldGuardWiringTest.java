package dev.twob2tkit.compat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Handle;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class MeteorFlightWorldGuardWiringTest {
	private static final String OWNER = "dev/twob2tkit/mixin/MeteorFlightWorldGuardMixin";
	private static final String TARGET = "Lnet/minecraft/client/player/LocalPlayer;isSpectator()Z";
	private ClassNode mixin() throws Exception {
		var result = new ClassNode();
		try (var stream = getClass().getResourceAsStream("/" + OWNER + ".class")) {
			assertNotNull(stream); new ClassReader(stream).accept(result, 0);
		}
		return result;
	}
	private AnnotationNode annotation(List<AnnotationNode> annotations, String descriptor) {
		return annotations.stream().filter(a -> a.desc.equals(descriptor)).findFirst().orElseThrow();
	}
	private List<AnnotationNode> annotations(List<AnnotationNode> visible, List<AnnotationNode> invisible) {
		var all = new ArrayList<AnnotationNode>();
		if (visible != null) all.addAll(visible);
		if (invisible != null) all.addAll(invisible);
		return all;
	}
	private Object value(AnnotationNode annotation, String key) {
		for (int i = 0; i < annotation.values.size(); i += 2)
			if (key.equals(annotation.values.get(i))) return annotation.values.get(i + 1);
		throw new AssertionError("Missing explicit annotation value " + key);
	}
	@Test void optionalHookTargetsOnlyTheExactDeactivatePlayerCallAndIsRegistered() throws Exception {
		var node = mixin();
		var classAnnotations = annotations(node.visibleAnnotations, node.invisibleAnnotations);
		assertNotNull(annotation(classAnnotations, "Lorg/spongepowered/asm/mixin/Pseudo;"));
		var target = annotation(classAnnotations, "Lorg/spongepowered/asm/mixin/Mixin;");
		assertEquals(List.of("meteordevelopment.meteorclient.systems.modules.movement.Flight"), value(target, "targets"));
		assertEquals(false, value(target, "remap"));
		var hook = node.methods.stream().filter(m -> m.name.equals("kit$skipMissingPlayerAbilities")).findFirst().orElseThrow();
		var redirect = annotation(annotations(hook.visibleAnnotations, hook.invisibleAnnotations), "Lorg/spongepowered/asm/mixin/injection/Redirect;");
		assertEquals(List.of("onDeactivate()V"), value(redirect, "method"));
		assertEquals(0, value(redirect, "require"), "Optional absent Meteor/site must not prevent client startup");
		assertEquals(false, value(redirect, "remap"));
		var at = (AnnotationNode) value(redirect, "at");
		assertEquals("INVOKE", value(at, "value")); assertEquals(TARGET, value(at, "target"));
		assertFalse(hook.desc.contains("CallbackInfo"), "No whole-method cancellation");
		String configuration = Files.readString(Path.of("src/client/resources/twob2tkit.client.mixins.json"));
		assertTrue(configuration.contains("\"MeteorFlightWorldGuardMixin\""));
	}
	@Test void receiverQueryIsLazyAndUsesOriginalIsSpectatorWithoutOtherWorldOrModuleActions() throws Exception {
		var node = mixin(); var calls = new ArrayList<MethodInsnNode>();
		for (var method : node.methods) for (var instruction : method.instructions)
			if (instruction instanceof MethodInsnNode call) calls.add(call);
		assertTrue(calls.stream().anyMatch(c -> c.owner.equals("dev/twob2tkit/compat/ClientWorldGuard")
			&& c.name.equals("spectatorOrMissingPlayer")));
		assertEquals(1, calls.stream().filter(c -> c.owner.equals("net/minecraft/client/player/LocalPlayer")
			&& c.name.equals("isSpectator") && c.desc.equals("()Z")).count());
		assertFalse(calls.stream().anyMatch(c -> List.of("requireNonNull", "getInstance", "cancel", "toggle",
			"setFlyingSpeed", "setPos", "send", "ready").contains(c.name)), "No eager null method reference, fake player or broad cleanup guard");
		assertTrue(node.methods.stream().flatMap(m -> java.util.stream.StreamSupport.stream(m.instructions.spliterator(), false))
			.anyMatch(i -> i instanceof InvokeDynamicInsnNode dynamic && java.util.Arrays.stream(dynamic.bsmArgs)
				.anyMatch(a -> a instanceof Handle h && h.getOwner().equals(OWNER) && h.getName().startsWith("lambda$"))));
	}
	@Test void installedMeteor42HasTheSingleExactCallAtTheObservedLine107() throws Exception {
		Path jar = Path.of(System.getProperty("kit.meteorJar",
			"/Applications/.minecraft/versions/26.1.2/mods/meteor-client-26.1.2-42.jar"));
		Assumptions.assumeTrue(Files.isRegularFile(jar), "Optional installed Meteor artifact was not supplied");
		try (var zip = new ZipFile(jar.toFile()); var in = zip.getInputStream(zip.getEntry(
			"meteordevelopment/meteorclient/systems/modules/movement/Flight.class"))) {
			var node = new ClassNode(); new ClassReader(in).accept(node, 0);
			var deactivate = node.methods.stream().filter(m -> m.name.equals("onDeactivate") && m.desc.equals("()V")).findFirst().orElseThrow();
			int targets = 0; boolean abilities = false, line107 = false;
			for (var instruction : deactivate.instructions) {
				if (instruction instanceof MethodInsnNode call) {
					if (call.owner.equals("net/minecraft/client/player/LocalPlayer") && call.name.equals("isSpectator") && call.desc.equals("()Z")) targets++;
					abilities |= call.name.equals("abilitiesOff") && call.desc.equals("()V");
				}
				if (instruction instanceof LineNumberNode line) line107 |= line.line == 107;
			}
			assertEquals(1, targets); assertTrue(abilities); assertTrue(line107);
		}
	}
}
