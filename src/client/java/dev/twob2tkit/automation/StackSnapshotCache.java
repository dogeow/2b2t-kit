package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.item.ItemStack;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.Predicate;

/** Client-thread stack serialization cache; scope and cursor changes invalidate every slot. */
public final class StackSnapshotCache {
    public static final int MAX_SLOTS = 200;
    private final Policy<ItemStack> cache = new Policy<>(MAX_SLOTS,
        StackSnapshotCache::copyStack, StackSnapshotCache::sameStack, StackSnapshotCache::cacheable);

    /** menuIdentity is the actual menu object, compared by identity rather than equals(). */
    public void begin(String worldSession, Object menuIdentity, int menuId, ItemStack cursor) {
        requireClientThread();
        cache.begin(worldSession, menuIdentity, menuId, cursor);
    }

    /** Use distinct keys for hand, inventory, equipment and menu slots. Serializer is read-only. */
    public JsonObject cached(String key, ItemStack stack, Function<ItemStack,JsonObject> serializer) {
        requireClientThread();
        return cache.cached(key, stack, serializer);
    }

    public void clear() { requireClientThread();cache.clear(); }

    private static void requireClientThread() {
        Minecraft client=Minecraft.getInstance();
        if(client==null || !client.isSameThread()) throw new IllegalStateException("Stack snapshots require the Minecraft client thread");
    }

    private static ItemStack copyStack(ItemStack stack) { return stack.copy(); }
    private static boolean sameStack(ItemStack previous, ItemStack current) {
        // 26.1.2 matches compares count, item and the complete component map, including damage.
        return ItemStack.matches(previous, current);
    }

    private static boolean cacheable(ItemStack stack) {
        // MapAutomation serializes live MapItemSavedData as well as item components.
        if (stack.has(DataComponents.MAP_ID)) return false;
        var contents = stack.get(DataComponents.CONTAINER);
        return contents == null || contents.nonEmptyItemCopyStream().limit(27)
            .noneMatch(child -> child.has(DataComponents.MAP_ID));
    }

    /** Independently testable cache mechanics; the public adapter always uses native copy/matches. */
    static final class Policy<S> {
        private record Entry<S>(S stack, JsonObject json) {}
        private final Function<S,S> copy;
        private final BiPredicate<S,S> same;
        private final Predicate<S> reusable;
        private final Map<String,Entry<S>> entries;
        private Thread thread;
        private boolean begun, scoped;
        private String world;
        private Object menu;
        private int menuId;
        private S cursor;

        Policy(int capacity, Function<S,S> copy, BiPredicate<S,S> same, Predicate<S> reusable) {
            if (capacity < 1 || capacity > MAX_SLOTS) throw new IllegalArgumentException("Invalid stack cache capacity");
            this.copy=Objects.requireNonNull(copy);this.same=Objects.requireNonNull(same);
            this.reusable=Objects.requireNonNull(reusable);
            entries=new LinkedHashMap<>(16,.75f,true) {
                @Override protected boolean removeEldestEntry(Map.Entry<String,Policy.Entry<S>> entry) {
                    return size()>capacity;
                }
            };
        }

        private void requireThread() {
            if (thread==null) thread=Thread.currentThread();
            else if (thread!=Thread.currentThread()) throw new IllegalStateException("Stack snapshots must remain on their client thread");
        }

        void begin(String worldSession, Object menuIdentity, int currentMenuId, S currentCursor) {
            requireThread();
            boolean valid=worldSession!=null && !worldSession.isBlank() && menuIdentity!=null
                && currentMenuId>=0 && currentCursor!=null;
            boolean changed=!valid || !scoped || !Objects.equals(world,worldSession) || menu!=menuIdentity
                || menuId!=currentMenuId || !same.test(cursor,currentCursor);
            if (changed) {
                entries.clear();cursor=valid?copy.apply(currentCursor):null;
            }
            world=worldSession;menu=menuIdentity;menuId=currentMenuId;scoped=valid;begun=true;
        }

        JsonObject cached(String key, S stack, Function<S,JsonObject> serializer) {
            requireThread();
            if (!begun) throw new IllegalStateException("Begin the current stack snapshot scope first");
            Objects.requireNonNull(key);Objects.requireNonNull(stack);Objects.requireNonNull(serializer);
            if (!scoped) {
                entries.remove(key);
                return Objects.requireNonNull(serializer.apply(copy.apply(stack))).deepCopy();
            }
            Entry<S> entry=entries.get(key);
            if (entry!=null && same.test(entry.stack,stack)) return entry.json.deepCopy();
            if (!reusable.test(stack)) {
                entries.remove(key);
                return Objects.requireNonNull(serializer.apply(copy.apply(stack))).deepCopy();
            }
            S frozen=copy.apply(stack);
            JsonObject json=Objects.requireNonNull(serializer.apply(copy.apply(frozen)));
            entries.put(key,new Entry<>(frozen,json.deepCopy()));
            return json.deepCopy();
        }

        void clear() {
            requireThread();entries.clear();begun=false;scoped=false;world=null;menu=null;cursor=null;
        }
        int size() { return entries.size(); }
    }
}
