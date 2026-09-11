package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;

/** Round trip at safe altitude. The excavation plan stays frozen until the original XZ is reached again. */
final class BorerCargoTrip {
	enum Stage { RISE, OUT, LOWER, SERVICE, RISE_BACK, BACK, DONE }
	private final BlockPos origin;
	private BlockPos depot;
	private double travelY;
	private Pose service;
	private boolean zFirst, travelled;
	private Stage stage = Stage.RISE;
	BorerCargoTrip(Pose p, BlockPos depot, int top) {
		origin = new BlockPos((int)Math.floor(p.x()), 0, (int)Math.floor(p.z()));
		this.depot = depot;
		service = new Pose(depot.getX() + .5, depot.getY() + 1.25, depot.getZ() + .5, 0, 0, 0);
		travelY = Math.max(p.y(), Math.max(top + 3.25, depot.getY() + 3.25));
	}
	BorerCargoTrip(Pose origin, BlockPos depot, BorerCargoRouting.Route route) {
		this.origin = new BlockPos((int)Math.floor(origin.x()), 0, (int)Math.floor(origin.z()));
		retarget(depot, route);
	}
	void retarget(BlockPos depot, BorerCargoRouting.Route route) {
		this.depot = depot; service = route.service(); travelY = route.travelY(); zFirst = route.zFirst();
		stage = route.here() ? Stage.SERVICE : Stage.RISE;
	}
	Stage stage() { return stage; }
	void returnToWork() { stage = travelled ? Stage.RISE_BACK : Stage.DONE; }
	void nextDepot(BlockPos next) { depot = next; service = new Pose(next.getX() + .5, next.getY() + 1.25, next.getZ() + .5, 0, 0, 0); travelY = Math.max(travelY, next.getY() + 3.25); stage = Stage.RISE; }
	Command step(World w, Pose p) {
		if (stage == Stage.DONE) return Command.waitAt(p, "卸货结束，继续原挖掘进度");
		if (stage == Stage.SERVICE) return Command.waitAt(p, "在卸货处集中处理背包");
		Command c;
		if (stage == Stage.RISE || stage == Stage.RISE_BACK) {
			c = vertical(w, p, travelY);
			if (c != null) return c;
			stage = stage == Stage.RISE ? Stage.OUT : Stage.BACK;
		} else if (stage == Stage.OUT || stage == Stage.BACK) {
			c = vertical(w, p, travelY); if (c != null) return c;
			double x = stage == Stage.OUT ? service.x() : origin.getX() + .5;
			double z = stage == Stage.OUT ? service.z() : origin.getZ() + .5;
			boolean zBeforeX = stage == Stage.OUT ? zFirst : !zFirst;
			if (zBeforeX && Math.abs(p.z() - z) > CENTER) return move(w, p, Action.Z, p.x(), p.y(), z);
			if (Math.abs(p.x() - x) > CENTER) return move(w, p, Action.X, x, p.y(), p.z());
			if (Math.abs(p.z() - z) > CENTER) return move(w, p, Action.Z, p.x(), p.y(), z);
			if (!p.settled()) return Command.waitAt(p, "卸货路线居中刹停");
			stage = stage == Stage.OUT ? Stage.LOWER : Stage.DONE;
		} else if (stage == Stage.LOWER) {
			c = vertical(w, p, service.y()); if (c != null) return c;
			stage = Stage.SERVICE;
		}
		return Command.waitAt(p, "卸货路线：" + stage);
	}
	private Command vertical(World w, Pose p, double y) {
		if (Math.abs(p.y() - y) <= HEIGHT) return p.settled() ? null : Command.waitAt(p, "卸货路线稳定高度");
		return move(w, p, y > p.y() ? Action.UP : Action.DOWN, p.x(), y, p.z());
	}
	private Command move(World w, Pose p, Action action, double x, double y, double z) {
		double nx = p.x() + Math.copySign(Math.min(.25, Math.abs(x - p.x())), x - p.x());
		double ny = p.y() + Math.copySign(Math.min(1.2, Math.abs(y - p.y())), y - p.y());
		double nz = p.z() + Math.copySign(Math.min(.25, Math.abs(z - p.z())), z - p.z());
		for (int by = (int)Math.floor(Math.min(p.y(), ny) + .001); by <= (int)Math.floor(Math.max(p.y(), ny) + 1.799); by++)
			for (int bx = (int)Math.floor(Math.min(p.x(), nx) - .299); bx <= (int)Math.floor(Math.max(p.x(), nx) + .299); bx++)
				for (int bz = (int)Math.floor(Math.min(p.z(), nz) - .299); bz <= (int)Math.floor(Math.max(p.z(), nz) + .299); bz++) {
					BlockPos b = new BlockPos(bx, by, bz); Cell cell = w.cell(b);
					if (cell == Cell.UNLOADED) return Command.waitAt(p, "卸货路线等待区块加载");
					if (cell == Cell.AIR) continue;
					// Only clear the departure shaft overhead, never tunnel sideways outside the selected excavation.
					if (stage == Stage.RISE && action == Action.UP && cell == Cell.SOLID
						&& b.getX() == origin.getX() && b.getZ() == origin.getZ() && !w.opensLiquid(b))
						return new Command(Action.MINE, b, p.x(), p.y(), p.z(), "清理原井上方卸货通道");
					return new Command(Action.BLOCKED, b, p.x(), p.y(), p.z(), "卸货路线受阻：" + cell + " @ " + BorerText.block(b));
				}
		travelled = true;
		return new Command(action, null, x, y, z, "前往卸货箱 / 返回原井");
	}
}
