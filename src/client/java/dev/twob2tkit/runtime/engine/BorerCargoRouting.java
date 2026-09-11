package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;

/** Validate outbound AND return legs before committing a depot. Never assumes a chest needs overhead access. */
final class BorerCargoRouting {
	record Route(Pose service, double travelY, boolean zFirst, boolean here) {}
	static Route choose(World w, Pose from, Pose origin, Pose service, int top) {
		boolean here = same(from, service);
		if (here && same(from, origin)) return new Route(service, from.y(), false, true);
		double low = Math.max(top + 1.05, service.y());
		double direct = Math.max(from.y(), service.y());
		for (double height : new double[]{direct, low, Math.max(from.y(), low), Math.max(from.y(), low) + 1}) {
			for (boolean zFirst : new boolean[]{false, true}) {
				Pose start = pose(from.x(), height, from.z());
				Pose end = pose(service.x(), height, service.z());
				Pose back = pose(Math.floor(origin.x()) + .5, height, Math.floor(origin.z()) + .5);
				if ((here || clear(w, from, start) && across(w, start, end, zFirst) && clear(w, end, service))
					&& clear(w, service, end) && across(w, end, back, !zFirst)) return new Route(service, height, zFirst, here);
			}
		}
		return null;
	}
	private static boolean across(World w, Pose a, Pose b, boolean zFirst) {
		Pose corner = zFirst ? pose(a.x(), a.y(), b.z()) : pose(b.x(), a.y(), a.z());
		return clear(w, a, corner) && clear(w, corner, b);
	}
	static boolean clear(World w, Pose a, Pose b) {
		for (int y = (int)Math.floor(Math.min(a.y(), b.y()) + .001); y <= (int)Math.floor(Math.max(a.y(), b.y()) + 1.799); y++)
			for (int x = (int)Math.floor(Math.min(a.x(), b.x()) - .299); x <= (int)Math.floor(Math.max(a.x(), b.x()) + .299); x++)
				for (int z = (int)Math.floor(Math.min(a.z(), b.z()) - .299); z <= (int)Math.floor(Math.max(a.z(), b.z()) + .299); z++)
					if (w.cell(new BlockPos(x, y, z)) != Cell.AIR) return false;
		return true;
	}
	static boolean same(Pose a, Pose b) { return Math.abs(a.x() - b.x()) < .001 && Math.abs(a.y() - b.y()) < .001 && Math.abs(a.z() - b.z()) < .001; }
	static Pose pose(double x, double y, double z) { return new Pose(x, y, z, 0, 0, 0); }
	static boolean worksiteChest(BlockPos chest, BlockPos min, BlockPos max) {
		return chest.getX() >= min.getX() - 6 && chest.getX() <= max.getX() + 6
			&& chest.getZ() >= min.getZ() - 6 && chest.getZ() <= max.getZ() + 6;
	}
	private BorerCargoRouting() {}
}
