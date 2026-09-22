package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;

/** Walking input follows the mining camera; body space and floor are verified independently. */
final class BorerAreaAdvance {
	interface World { boolean air(BlockPos p); boolean floor(BlockPos p); }
	record Input(boolean forward, boolean back, boolean left, boolean right, double dx, double dz) {
		boolean moving() { return forward || back || left || right; }
	}
	static final Input STILL = new Input(false,false,false,false,0,0);
	static Input input(BorerAreaPlan.Pose p, BlockPos goal, float yaw) {
		if (goal == null) return STILL;
		double dx = goal.getX()+.5-p.x(), dz = goal.getZ()+.5-p.z();
		double distance = Math.hypot(dx,dz);
		if (distance < .28) return STILL;
		dx /= distance; dz /= distance;
		double radians = Math.toRadians(yaw), s = Math.sin(radians), c = Math.cos(radians);
		double front = -s*dx+c*dz, left = c*dx+s*dz;
		double diagonal = Math.sin(Math.PI/8);
		int f = front > diagonal ? 1 : front < -diagonal ? -1 : 0;
		int l = left > diagonal ? 1 : left < -diagonal ? -1 : 0;
		double length = Math.hypot(f,l);
		if (length == 0) return STILL;
		return new Input(f>0,f<0,l>0,l<0,(l*c-f*s)/length,(l*s+f*c)/length);
	}
	static boolean safe(World world, BorerAreaPlan.Pose p, int bottom, Input input) {
		if (!input.moving() || p.y() < bottom-.02 || p.y() > bottom+.12 || Math.abs(p.vy()) > .085 || Math.hypot(p.vx(),p.vz())>1.5) return false;
		// Covers normal walking/sprint input plus incoming momentum; no position or velocity is forced.
		double dx = input.dx()*.65+p.vx(), dz = input.dz()*.65+p.vz();
		// Include coasting as well as the requested input; opposite directions must not cancel the safety probe.
		double minX=Math.min(p.x(),Math.min(p.x()+p.vx(),p.x()+dx)), maxX=Math.max(p.x(),Math.max(p.x()+p.vx(),p.x()+dx));
		double minZ=Math.min(p.z(),Math.min(p.z()+p.vz(),p.z()+dz)), maxZ=Math.max(p.z(),Math.max(p.z()+p.vz(),p.z()+dz));
		for(int bx=(int)Math.floor(minX-.299);bx<=(int)Math.floor(maxX+.299);bx++)
			for(int bz=(int)Math.floor(minZ-.299);bz<=(int)Math.floor(maxZ+.299);bz++) {
					if (!world.floor(new BlockPos(bx,bottom-1,bz))) return false;
					for(int by=(int)Math.floor(p.y()+.001);by<=(int)Math.floor(p.y()+1.799);by++)
						if (!world.air(new BlockPos(bx,by,bz))) return false;
		}
		return true;
	}
	private BorerAreaAdvance() {}
}
