package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Handle;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

final class StackSnapshotCacheTest {
    private static final class Stack {
        String item="minecraft:iron_sword";
        int count=1,damage;
        boolean liveMap;
        final Map<String,String> components=new HashMap<>();
        Stack copy() {
            Stack copy=new Stack();copy.item=item;copy.count=count;copy.damage=damage;
            copy.liveMap=liveMap;copy.components.putAll(components);return copy;
        }
        boolean same(Stack other) {
            return item.equals(other.item) && count==other.count && damage==other.damage
                && liveMap==other.liveMap && components.equals(other.components);
        }
    }
    private static final class Fixture {
        final StackSnapshotCache.Policy<Stack> cache;
        final AtomicInteger formats=new AtomicInteger();
        final Stack cursor=new Stack(),held=new Stack();
        final Object menu=new Object();
        JsonObject retainedJson;
        Stack retainedInput;
        boolean mapLoaded;
        Fixture() { this(StackSnapshotCache.MAX_SLOTS); }
        Fixture(int capacity) {
            cache=new StackSnapshotCache.Policy<>(capacity,Stack::copy,Stack::same,s->!s.liveMap);
            cache.begin("world-1",menu,0,cursor);
        }
        JsonObject serialize(Stack stack) {
            formats.incrementAndGet();retainedInput=stack;
            JsonObject out=new JsonObject();out.addProperty("item",stack.item);out.addProperty("count",stack.count);
            out.addProperty("damage",stack.damage);out.addProperty("map_loaded",mapLoaded);
            out.addProperty("components",stack.components.toString());
            JsonArray children=new JsonArray();JsonObject child=new JsonObject();child.addProperty("count",2);children.add(child);
            out.add("contains",children);retainedJson=out;return out;
        }
        JsonObject cached(String key) { return cache.cached(key,held,this::serialize); }
    }

    @Test void unchangedStackIsSerializedOnceAndEveryCallerGetsAnIndependentDeepCopy() {
        Fixture f=new Fixture();JsonObject first=f.cached("inventory:0");first.addProperty("slot",7);
        first.getAsJsonArray("contains").get(0).getAsJsonObject().addProperty("count",99);
        f.retainedJson.addProperty("item","mutated serializer output");
        JsonObject next=f.cached("inventory:0");
        assertEquals(1,f.formats.get());assertFalse(next.has("slot"));
        assertEquals("minecraft:iron_sword",next.get("item").getAsString());
        assertEquals(2,next.getAsJsonArray("contains").get(0).getAsJsonObject().get("count").getAsInt());
        assertNotSame(first,next);
    }

    @Test void countDamageItemAndEachComponentChangeImmediatelyRefreshTheAffectedSlot() {
        Fixture f=new Fixture();f.cached("hand");
        f.held.count=2;assertEquals(2,f.cached("hand").get("count").getAsInt());
        f.held.damage=3;assertEquals(3,f.cached("hand").get("damage").getAsInt());
        f.held.item="minecraft:diamond_sword";assertEquals(f.held.item,f.cached("hand").get("item").getAsString());
        for(String component:List.of("name","enchantments","potion","map_id","container","custom_data")) {
            f.held.components.put(component,"new actual value");
            assertTrue(f.cached("hand").get("components").getAsString().contains(component));
        }
        assertEquals(10,f.formats.get());
        f.held.components.remove("enchantments");f.cached("hand");assertEquals(11,f.formats.get());
    }

    @Test void cachedComparisonSnapshotIsNotAliasedToTheSerializerOrTheLiveInput() {
        Fixture f=new Fixture();f.cached("hand");f.retainedInput.count=5;
        f.held.count=5;
        assertEquals(5,f.cached("hand").get("count").getAsInt());assertEquals(2,f.formats.get());
        f.held.components.put("name","later");f.cached("hand");assertEquals(3,f.formats.get());
    }

    @Test void worldMenuIdentityMenuIdAndCursorChangesClearEverySlot() {
        Fixture f=new Fixture();f.cached("inventory:0");f.cached("menu:0");
        f.cache.begin("world-1",f.menu,0,f.cursor);f.cached("inventory:0");assertEquals(2,f.formats.get());
        f.cache.begin("world-2",f.menu,0,f.cursor);f.cached("inventory:0");f.cached("menu:0");
        assertEquals(4,f.formats.get());
        Object nextMenu=new Object();f.cache.begin("world-2",nextMenu,0,f.cursor);f.cached("inventory:0");f.cached("menu:0");
        assertEquals(6,f.formats.get());
        f.cache.begin("world-2",nextMenu,1,f.cursor);f.cached("inventory:0");f.cached("menu:0");assertEquals(8,f.formats.get());
        f.cursor.count=2;f.cache.begin("world-2",nextMenu,1,f.cursor);f.cached("inventory:0");f.cached("menu:0");
        assertEquals(10,f.formats.get());
        f.cursor.components.put("name","cursor changed");f.cache.begin("world-2",nextMenu,1,f.cursor);
        f.cached("inventory:0");f.cached("menu:0");assertEquals(12,f.formats.get());
    }

    @Test void cursorAndSlotEqualityCannotReplaceActualMenuObjectIdentity() {
        Fixture f=new Fixture();
        class Menu { @Override public boolean equals(Object other) { return other instanceof Menu; } }
        Menu first=new Menu(),next=new Menu();assertEquals(first,next);
        f.cache.begin("world-1",first,0,f.cursor);f.cached("inventory:0");
        f.cache.begin("world-1",next,0,f.cursor);f.cached("inventory:0");assertEquals(2,f.formats.get());
    }

    @Test void unknownScopeAndLiveMapMetadataAlwaysUseFreshSerialization() {
        Fixture f=new Fixture();f.cached("hand");f.held.liveMap=true;f.mapLoaded=false;
        assertFalse(f.cached("hand").get("map_loaded").getAsBoolean());f.mapLoaded=true;
        assertTrue(f.cached("hand").get("map_loaded").getAsBoolean());assertEquals(0,f.cache.size());
        f.held.liveMap=false;f.cache.begin("",f.menu,0,f.cursor);f.cached("hand");f.cached("hand");
        assertEquals(5,f.formats.get());assertEquals(0,f.cache.size());
        f.cache.begin("world-1",f.menu,0,null);f.cached("hand");f.cached("hand");assertEquals(7,f.formats.get());
    }

    @Test void capacityIsBoundedAndLeastRecentlyUsedEntriesAreEvicted() {
        Fixture f=new Fixture(2);f.cached("a");f.cached("b");f.cached("a");f.cached("c");
        assertEquals(3,f.formats.get());assertEquals(2,f.cache.size());
        f.cached("a");assertEquals(3,f.formats.get());f.cached("b");assertEquals(4,f.formats.get());
        f.cache.clear();assertEquals(0,f.cache.size());
        assertThrows(IllegalStateException.class,()->f.cached("a"));
    }

    @Test void anotherThreadIsRejectedBeforeStackCopyComparisonOrSerialization() throws Exception {
        Fixture f=new Fixture();AtomicReference<Throwable> error=new AtomicReference<>();
        Thread other=new Thread(()->{try {f.cached("hand");} catch(Throwable failure) {error.set(failure);}});
        other.start();other.join(2000);assertFalse(other.isAlive());
        assertInstanceOf(IllegalStateException.class,error.get());assertEquals(0,f.formats.get());
    }

    @Test void nativeAdapterUsesActualMinecraftCopyAndFullMatchesAndExcludesDynamicMaps() throws Exception {
        String owner="dev/twob2tkit/automation/StackSnapshotCache";
        var same=calls(owner,"sameStack");assertTrue(same.contains("net/minecraft/world/item/ItemStack.matches"));
        assertTrue(calls(owner,"copyStack").contains("net/minecraft/world/item/ItemStack.copy"));
        var constructor=calls(owner,"<init>");
        assertTrue(constructor.contains(owner+".sameStack"));assertTrue(constructor.contains(owner+".copyStack"));
        assertTrue(constructor.contains(owner+".cacheable"));
        var cacheable=calls(owner,"cacheable");
        assertTrue(cacheable.contains("net/minecraft/core/component/DataComponents.MAP_ID"));
        assertTrue(cacheable.contains("net/minecraft/core/component/DataComponents.CONTAINER"));
        var actualMatches=calls("net/minecraft/world/item/ItemStack","matches");
        assertTrue(actualMatches.contains("net/minecraft/world/item/ItemStack.getCount"));
        assertTrue(actualMatches.contains("net/minecraft/world/item/ItemStack.isSameItemSameComponents"));
        assertTrue(calls("net/minecraft/world/item/ItemStack","isSameItemSameComponents").contains("java/util/Objects.equals"));
        assertTrue(calls(owner,"begin").contains(owner+".requireClientThread"));
        assertTrue(calls(owner,"cached").contains(owner+".requireClientThread"));
        assertTrue(calls(owner,"requireClientThread").stream().anyMatch(call->call.endsWith(".isSameThread")));
    }

    private static List<String> calls(String owner,String method) throws Exception {
        List<String> result=new ArrayList<>();
        try(InputStream input=StackSnapshotCacheTest.class.getClassLoader().getResourceAsStream(owner+".class")) {
            assertNotNull(input);
            new ClassReader(input).accept(new ClassVisitor(Opcodes.ASM9) {
                @Override public MethodVisitor visitMethod(int access,String name,String desc,String signature,String[] exceptions) {
                    if(!name.equals(method)) return null;
                    return new MethodVisitor(Opcodes.ASM9) {
                        @Override public void visitMethodInsn(int opcode,String owner,String name,String desc,boolean itf) { result.add(owner+"."+name); }
                        @Override public void visitFieldInsn(int opcode,String owner,String name,String desc) { result.add(owner+"."+name); }
                        @Override public void visitInvokeDynamicInsn(String name,String desc,Handle bsm,Object... args) {
                            for(Object argument:args) if(argument instanceof Handle handle) result.add(handle.getOwner()+"."+handle.getName());
                        }
                    };
                }
            },0);
        }
        return result;
    }
}
