package dev.twob2tkit.runtime.engine;

import java.util.*;

/** Every chunk intersecting the requested block-radius circle, in centre-out square-spiral order. */
final class SceneryCoverage {
	static final int MIN_RADIUS = 16, LEGACY_RADIUS = 4096, MAX_RADIUS = 32768;
	record Chunk(int x, int z) { long key() { return ((long)x << 32) ^ (z & 0xffffffffL); } }
	final double centreX, centreZ;
	final int radius;
	private final List<Chunk> chunks;
	private final SceneryChunkRows rows;
	private final Map<Long, Integer> indices;
	private final BitSet confirmed = new BitSet(), submitted = new BitSet();
	private int cursor, confirmedCount, submittedCount, outsideConfirmed, outsideTotal, outsideSubmitted;
	private final BitSet outside = new BitSet();
	private ChunkBounds bounds;
	record ChunkBounds(int minX,int maxX,int minZ,int maxZ) {
		static ChunkBounds inside(double minX,double maxX,double minZ,double maxZ) {
			// Keep the target centre far enough inside for the body sweep and braking.
			return new ChunkBounds(firstInside(minX),lastInside(maxX),firstInside(minZ),lastInside(maxZ));
		}
		private static int firstInside(double edge) { return (int)Math.ceil((edge+3-8)/16); }
		private static int lastInside(double edge) { return (int)Math.floor((edge-3-8)/16); }
		boolean contains(int x,int z) { return x>=minX && x<=maxX && z>=minZ && z<=maxZ; }
	}

	boolean clipTo(ChunkBounds next) {
		if (next.equals(bounds)) return false;
		bounds=next;
		outside.clear();
		if (rows!=null) rows.clip(next,outside);
		else for (int i=0;i<chunks.size();i++) {
			var p=chunks.get(i);
			if (!next.contains(p.x(),p.z())) outside.set(i);
		}
		var coveredOutside=(BitSet)confirmed.clone();
		coveredOutside.and(outside);
		outsideConfirmed=coveredOutside.cardinality();
		outsideTotal=outside.cardinality();
		outsideSubmitted=0;
		for (int i=submitted.nextSetBit(0);i>=0;i=submitted.nextSetBit(i+1))
			if (outside.get(i)) outsideSubmitted++;
		cursor=0;
		return true;
	}

    boolean missingForMap(int x, int z) {
        int i = index(x, z);
        return i >= 0 && !outside.get(i) && !confirmed.get(i);
    }

	int skippedOutside() { return outsideTotal; }

	SceneryCoverage(double x, double z, int radius) {
		if (!Double.isFinite(x) || !Double.isFinite(z) || Math.abs(x) >= 30_000_000 || Math.abs(z) >= 30_000_000
			|| radius < MIN_RADIUS || radius > MAX_RADIUS) throw new IllegalArgumentException("半径须为 16–32768 格，且圆心须在有效地图坐标内");
		centreX = x; centreZ = z; this.radius = radius;
		rows=radius>LEGACY_RADIUS ? new SceneryChunkRows(x,z,radius) : null;
		chunks=rows==null ? new ArrayList<>() : rows;
		indices=rows==null ? new HashMap<>() : Map.of();
		if (rows!=null) return;
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
	SceneryCoverage expanded(int newRadius) {
		if (newRadius<=radius) throw new IllegalArgumentException("扩圈半径必须大于上次半径");
		var result=new SceneryCoverage(centreX,centreZ,newRadius);
		if (rows!=null) {
			rows.copyConfirmedTo(result.rows,confirmed,result.confirmed);
			result.confirmedCount=confirmedCount;
			result.rows.restore(result.confirmed);
		} else for (int i=confirmed.nextSetBit(0);i>=0;i=confirmed.nextSetBit(i+1))
			result.reuse(chunks.get(i));
		return result;
	}
	void reuse(Chunk pos) {
		int i=index(pos.x(),pos.z());
		if (i>=0 && !outside.get(i) && !confirmed.get(i) && !submitted.get(i)) {
			confirmed.set(i); confirmedCount++;
			if (rows!=null) rows.markConfirmed(i);
		}
	}
	int total() { return chunks.size()-skippedOutside(); }
	int confirmed() { return confirmedCount-outsideConfirmed; }
	int submitted() { return submittedCount; }
	int insideSubmitted() { return submittedCount-outsideSubmitted; }
	boolean complete() { return confirmed() == total(); }
	boolean needs(int x, int z) {
		int i=index(x,z); return i >= 0 && !outside.get(i) && !confirmed.get(i) && !submitted.get(i);
	}
	void accepted(int x, int z) {
		int i=index(x,z);
		if (i >= 0 && !outside.get(i) && !confirmed.get(i) && !submitted.get(i)) { submitted.set(i); submittedCount++; }
	}
	void commitBatch() {
		for (int i=submitted.nextSetBit(0);i>=0;i=submitted.nextSetBit(i+1)) {
			if (rows!=null) rows.markConfirmed(i);
			if (outside.get(i)) outsideConfirmed++;
		}
		confirmed.or(submitted);
		confirmedCount += submittedCount;
		submitted.clear(); submittedCount = outsideSubmitted = 0;
	}
	Chunk next() {
		while (cursor < chunks.size() && (outside.get(cursor) || confirmed.get(cursor) || submitted.get(cursor))) cursor++;
		return cursor == chunks.size() ? null : chunks.get(cursor);
	}
	/** Keep the active target until covered; then pick the closest gap from the actual position.
	 * Keep the original spiral indices because saved checkpoints refer to them. */
	Chunk nextNearest(Chunk current, double x, double z) {
		if (current != null && needs(current.x(), current.z())) return current;
		if (complete()) return null;
		if (rows!=null) return rows.nearest(x,z,confirmed,submitted,bounds);
		Chunk best = null;
		double bestDistance = Double.POSITIVE_INFINITY;
		for (int i=confirmed.nextClearBit(0); i<chunks.size(); i=confirmed.nextClearBit(i+1)) {
			if (outside.get(i) || submitted.get(i)) continue;
			Chunk candidate=chunks.get(i);
			double dx=candidate.x()*16.0+8-x, dz=candidate.z()*16.0+8-z;
			double distance=dx*dx+dz*dz;
			if (distance < bestDistance) {
				best=candidate;
				bestDistance=distance;
			}
		}
		return best;
	}
	/** Largest radius whose circle plus its edge chunk stays inside the border; below MIN_RADIUS means no task fits. */
	static int maxRadiusInside(double x, double z, double minX, double maxX, double minZ, double maxZ) {
		double room = Math.min(Math.min(x - minX, maxX - x), Math.min(z - minZ, maxZ - z)) - 17;
		return (int)Math.max(0, Math.min(MAX_RADIUS, Math.floor(room)));
	}
	private int index(int x,int z) {
		return rows==null ? indices.getOrDefault(new Chunk(x,z).key(),-1) : rows.indexOf(x,z);
	}
	List<Chunk> chunks() { return Collections.unmodifiableList(chunks); }
	List<Chunk> missingInRegion(int rx,int rz) {
		var missing=new ArrayList<Chunk>();
		for (int z=rz*32;z<rz*32+32;z++) for (int x=rx*32;x<rx*32+32;x++)
			if (needs(x,z)) missing.add(new Chunk(x,z));
		return missing;
	}
	Chunk nearestInRegion(int rx,int rz,double x,double z) {
		Chunk best=null; double distance=Double.POSITIVE_INFINITY;
		for (int cz=rz*32;cz<rz*32+32;cz++) for (int cx=rx*32;cx<rx*32+32;cx++) {
			if (!needs(cx,cz)) continue;
			double dx=cx*16.0+8-x,dz=cz*16.0+8-z,d=dx*dx+dz*dz;
			if (d<distance) { distance=d; best=new Chunk(cx,cz); }
		}
		return best;
	}
	long[] checkpoint() { return confirmed.toLongArray(); }
	void restore(long[] bits) {
		BitSet value = BitSet.valueOf(bits == null ? new long[0] : bits);
		if (value.length() > chunks.size()) throw new IllegalArgumentException("风景进度超出本次范围");
		confirmed.clear(); confirmed.or(value); confirmedCount = confirmed.cardinality(); submitted.clear(); submittedCount = outsideSubmitted = 0; cursor = 0;
		if (rows!=null) rows.restore(confirmed);
		if (bounds!=null) {
			var old=bounds; bounds=null;
			clipTo(old);
		}
	}
}
