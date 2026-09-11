package dev.twob2tkit.runtime.engine;

import java.util.*;

/** Every chunk intersecting the requested block-radius circle, in centre-out square-spiral order. */
final class SceneryCoverage {
	static final int MIN_RADIUS = 16, MAX_RADIUS = 4096;
	record Chunk(int x, int z) { long key() { return ((long)x << 32) ^ (z & 0xffffffffL); } }
	final double centreX, centreZ;
	final int radius;
	private final List<Chunk> chunks = new ArrayList<>();
	private final Map<Long, Integer> indices = new HashMap<>();
	private final BitSet confirmed = new BitSet(), submitted = new BitSet();
	private int cursor, confirmedCount, submittedCount;
	SceneryCoverage(double x, double z, int radius) {
		if (!Double.isFinite(x) || !Double.isFinite(z) || Math.abs(x) + radius >= 29_999_900 || Math.abs(z) + radius >= 29_999_900
			|| radius < MIN_RADIUS || radius > MAX_RADIUS) throw new IllegalArgumentException("半径须为 16–4096 格，且范围不能越过世界坐标边界");
		centreX = x; centreZ = z; this.radius = radius;
		int cx = (int)Math.floor(x / 16), cz = (int)Math.floor(z / 16), rings = (int)Math.ceil(radius / 16.0) + 1;
		add(cx, cz);
		for (int ring = 1; ring <= rings; ring++) {
			for (int dx = -ring + 1; dx <= ring; dx++) add(cx + dx, cz - ring);
			for (int dz = -ring + 1; dz <= ring; dz++) add(cx + ring, cz + dz);
			for (int dx = ring - 1; dx >= -ring; dx--) add(cx + dx, cz + ring);
			for (int dz = ring - 1; dz >= -ring; dz--) add(cx - ring, cz + dz);
		}
	}
	private void add(int x, int z) {
		double dx = Math.max(Math.max(x * 16.0 - centreX, centreX - (x * 16.0 + 16)), 0);
		double dz = Math.max(Math.max(z * 16.0 - centreZ, centreZ - (z * 16.0 + 16)), 0);
		if (dx * dx + dz * dz > (double)radius * radius) return;
		Chunk chunk = new Chunk(x, z); indices.put(chunk.key(), chunks.size()); chunks.add(chunk);
	}
	int total() { return chunks.size(); }
	int confirmed() { return confirmedCount; }
	int submitted() { return submittedCount; }
	boolean complete() { return confirmed() == total(); }
	boolean needs(int x, int z) {
		Integer i = indices.get(new Chunk(x, z).key()); return i != null && !confirmed.get(i) && !submitted.get(i);
	}
	void accepted(int x, int z) {
		Integer i = indices.get(new Chunk(x, z).key());
		if (i != null && !confirmed.get(i) && !submitted.get(i)) { submitted.set(i); submittedCount++; }
	}
	void commitBatch() { confirmed.or(submitted); confirmedCount += submittedCount; submitted.clear(); submittedCount = 0; }
	Chunk next() {
		while (cursor < chunks.size() && (confirmed.get(cursor) || submitted.get(cursor))) cursor++;
		return cursor == chunks.size() ? null : chunks.get(cursor);
	}
	List<Chunk> chunks() { return List.copyOf(chunks); }
	long[] checkpoint() { return confirmed.toLongArray(); }
	void restore(long[] bits) {
		BitSet value = BitSet.valueOf(bits == null ? new long[0] : bits);
		if (value.length() > total()) throw new IllegalArgumentException("风景进度超出本次范围");
		confirmed.clear(); confirmed.or(value); confirmedCount = confirmed.cardinality(); submitted.clear(); submittedCount = 0; cursor = 0;
	}
}
