package dev.twob2tkit.structure;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

/** Shared budget covers base samples and every nested structure classifier. */
public final class SeedScoutScanBudget<T> {
    public static final int READS_PER_TICK = 128;
    public static final int INSPECTIONS_PER_TICK = 64;
    public static final int CACHE_TICKS = 200;
    public static final int BLOCK_CACHE_SIZE = 4096;
    public static final int SURFACE_CACHE_SIZE = 512;
    public static final class Exhausted extends RuntimeException {
        private Exhausted() { super(null, null, false, false); }
    }
    private record Sample<V>(long tick, V value) {}
    private final Map<Long,Sample<T>> blocks = cache(BLOCK_CACHE_SIZE);
    private final Map<Long,Sample<Integer>> surfaces = cache(SURFACE_CACHE_SIZE);
    private long tick;
    private int reads, inspections;
    private static <V> Map<Long,Sample<V>> cache(int size) {
        return new LinkedHashMap<>(16,.75f,true) {
            @Override protected boolean removeEldestEntry(Map.Entry<Long,Sample<V>> entry) {
                return size() > size;
            }
        };
    }
    public static boolean shouldScan(boolean enabled, boolean needed, boolean hasSeed) {
        return enabled && needed && !hasSeed;
    }
    public void beginTick(long tick) { this.tick=tick; reads=0; inspections=0; }
    public boolean inspect() {
        if (inspections>=INSPECTIONS_PER_TICK) return false;
        inspections++; return true;
    }
    private void charge() {
        if (reads>=READS_PER_TICK) throw new Exhausted();
        reads++;
    }
    private <V> V read(Map<Long,Sample<V>> cache,long key,Supplier<V> loader) {
        Sample<V> sample=cache.get(key);
        if(sample!=null && tick>=sample.tick && tick-sample.tick<CACHE_TICKS) return sample.value;
        charge();V value=loader.get();cache.put(key,new Sample<>(tick,value));return value;
    }
    public T block(long key,Supplier<T> loader) { return read(blocks,key,loader); }
    public int surface(long key,Supplier<Integer> loader) { return read(surfaces,key,loader); }
    public <V> V uncached(Supplier<V> loader) { charge();return loader.get(); }
    public int reads() { return reads; }
    public int cachedBlocks() { return blocks.size(); }
    public void clear() { blocks.clear();surfaces.clear();reads=0;inspections=0; }
}
