package dev.twob2tkit.runtime.engine;

import java.util.AbstractList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.Objects;

/** Dense circle index with one span per Z row, independent of the covered area. */
final class SceneryChunkRows extends AbstractList<SceneryCoverage.Chunk> {
	private final int minZ;
	private final int[] starts, west, confirmedCounts;

	SceneryChunkRows(double x, double z, int radius) {
		minZ=(int)Math.ceil((z-radius)/16)-1;
		int maxZ=(int)Math.floor((z+radius)/16);
		starts=new int[maxZ-minZ+2];
		west=new int[starts.length-1];
		confirmedCounts=new int[west.length];
		for (int row=0;row<west.length;row++) {
			int chunkZ=minZ+row;
			double dz=Math.max(0,Math.max(chunkZ*16.0-z,z-(chunkZ*16.0+16)));
			double dx=Math.sqrt(Math.max(0,(double)radius*radius-dz*dz));
			west[row]=(int)Math.ceil((x-dx)/16)-1;
			int east=(int)Math.floor((x+dx)/16);
			starts[row+1]=starts[row]+east-west[row]+1;
		}
	}

	@Override public int size() { return starts[west.length]; }

	@Override public SceneryCoverage.Chunk get(int index) {
		Objects.checkIndex(index,size());
		int row=rowFor(index);
		return new SceneryCoverage.Chunk(west[row]+index-starts[row],minZ+row);
	}

	private int rowFor(int index) {
		int row=Arrays.binarySearch(starts,index);
		return row<0 ? -row-2 : row;
	}

	void markConfirmed(int index) { confirmedCounts[rowFor(index)]++; }

	void restore(BitSet confirmed) {
		for (int row=0;row<west.length;row++)
			confirmedCounts[row]=confirmed.get(starts[row],starts[row+1]).cardinality();
	}

	void copyConfirmedTo(SceneryChunkRows expanded, BitSet source, BitSet target) {
		for (int row=0;row<west.length;row++) {
			int end=starts[row+1];
			int shift=expanded.indexOf(west[row],minZ+row)-starts[row];
			for (int start=source.nextSetBit(starts[row]);start>=0 && start<end;) {
				int stop=Math.min(end,source.nextClearBit(start));
				target.set(start+shift,stop+shift);
				if (stop==end) break;
				start=source.nextSetBit(stop);
			}
		}
	}

	int indexOf(int x,int z) {
		int row=z-minZ;
		if (row<0 || row>=west.length || x<west[row]) return -1;
		int index=starts[row]+x-west[row];
		return index<starts[row+1] ? index : -1;
	}

	void clip(SceneryCoverage.ChunkBounds bounds,BitSet outside) {
		for (int row=0;row<west.length;row++) {
			int start=starts[row], end=starts[row+1], z=minZ+row;
			int first=Math.max(start, Math.min(end,start+bounds.minX()-west[row]));
			int last=Math.max(start, Math.min(end,start+bounds.maxX()-west[row]+1));
			if (z<bounds.minZ() || z>bounds.maxZ() || first>=last) outside.set(start,end);
			else { outside.set(start,first); outside.set(last,end); }
		}
	}

	SceneryCoverage.Chunk nearest(double x,double z,BitSet confirmed,BitSet submitted, SceneryCoverage.ChunkBounds bounds) {
		double best=Double.POSITIVE_INFINITY;
		int picked=-1;
		for (int row=0;row<west.length;row++) {
			if (confirmedCounts[row]==starts[row+1]-starts[row]) continue;
			double dz=(minZ+row)*16.0+8-z, dzSquared=dz*dz;
			if (dzSquared>=best) continue;
			int start=starts[row], first=start, end=starts[row+1];
			if (bounds!=null) {
				int chunkZ=minZ+row;
				if (chunkZ<bounds.minZ() || chunkZ>bounds.maxZ()) continue;
				first=Math.max(first,start+bounds.minX()-west[row]);
				end=Math.min(end,start+bounds.maxX()-west[row]+1);
				if (first>=end) continue;
			}
			int middle=Math.max(first,Math.min(end-1,start+(int)Math.floor((x-8)/16)-west[row]));
			int left=confirmed.previousClearBit(middle);
			while (left>=first && submitted.get(left)) left=confirmed.previousClearBit(left-1);
			int right=confirmed.nextClearBit(middle+1);
			while (right<end && submitted.get(right)) right=confirmed.nextClearBit(right+1);
			for (int index : new int[]{left,right}) {
				if (index<first || index>=end) continue;
				double dx=(west[row]+index-start)*16.0+8-x;
				double distance=dx*dx+dzSquared;
				if (distance<best) { best=distance; picked=index; }
			}
		}
		return picked<0 ? null : get(picked);
	}
}
