package dev.twob2tkit.borer;

import dev.twob2tkit.runtime.api.BuildNavigation;
import dev.twob2tkit.runtime.engine.DefaultBuildNavigation;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.*;
import java.util.*;
import java.util.jar.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerEngineLoadingTest {
    @TempDir Path directory;

    @Test void actualLoaderRejectsMissingAndTruncatedEngineClassesInsteadOfUsingBundledCopies() throws Exception {
        String name=DefaultBuildNavigation.class.getName();
        Path jar=directory.resolve("engine.jar");
        writeJar(jar,null);
        try(var loader=loader(jar)) {
            assertThrows(ClassNotFoundException.class,()->loader.loadClass(name));
        }
        writeJar(jar,new byte[]{(byte)0xca,(byte)0xfe,(byte)0xba,(byte)0xbe});
        try(var loader=loader(jar)) {
            assertThrows(ClassFormatError.class,()->loader.loadClass(name));
        }
        try(var input=DefaultBuildNavigation.class.getResourceAsStream("DefaultBuildNavigation.class")) {
            assertNotNull(input);writeJar(jar,input.readAllBytes());
        }
        try(var loader=loader(jar)) {
            var type=loader.loadClass(name);
            assertSame(loader,type.getClassLoader());
            java.util.function.Predicate<BlockPos> clear=p->true;
            var navigation=(BuildNavigation)type.getConstructor(java.util.function.Predicate.class).newInstance(clear);
            assertTrue(navigation.stations(BlockPos.ZERO).contains(new BlockPos(0,1,0)));
        }
    }

    @Test void actualReloadValidatesTheCandidateBeforeStoppingTheCurrentEngine() throws Exception {
        var external=calls("loadExternalEngine");
        assertTrue(external.containsAll(List.of("copy","preloadEngineClasses","newInstance")));
        assertTrue(external.indexOf("copy")<external.indexOf("preloadEngineClasses"));
        assertTrue(external.indexOf("preloadEngineClasses")<external.indexOf("newInstance"));
        assertTrue(external.containsAll(List.of("requiredHostApiVersion","apiVersion","runtimeVersion","isBlank")));
        var reload=calls("reload");
        assertTrue(reload.containsAll(List.of("loadExternalEngine","runtimeVersion","stop")));
        assertTrue(reload.indexOf("loadExternalEngine")<reload.indexOf("stop"));
        assertTrue(reload.indexOf("runtimeVersion")<reload.indexOf("stop"));
        assertTrue(reload.contains("closeQuietly"));
    }

    private void writeJar(Path path,byte[] navigation) throws Exception {
        try(var output=new JarOutputStream(Files.newOutputStream(path))) {
            if(navigation==null)return;
            output.putNextEntry(new JarEntry("dev/twob2tkit/runtime/engine/DefaultBuildNavigation.class"));
            output.write(navigation);output.closeEntry();
        }
    }
    private URLClassLoader loader(Path jar) throws Exception {
        var type=Class.forName("dev.twob2tkit.borer.TunnelBorer$ChildFirstEngineLoader");
        var constructor=type.getDeclaredConstructor(URL[].class,ClassLoader.class);
        constructor.setAccessible(true);
        return (URLClassLoader)constructor.newInstance(new URL[]{jar.toUri().toURL()},getClass().getClassLoader());
    }
    private static List<String> calls(String name) throws Exception {
        var node=new ClassNode();
        try(var input=BorerEngineLoadingTest.class.getResourceAsStream("/dev/twob2tkit/borer/TunnelBorer.class")) {
            assertNotNull(input);new ClassReader(input).accept(node,0);
        }
        var method=node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
        List<String> calls=new ArrayList<>();
        for(var instruction:method.instructions)if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        return calls;
    }
}
