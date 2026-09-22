package dev.twob2tkit.chopper;

/** Safety transitions shared by the actual scaffold runner and its replay tests. */
final class ChopperSupportPolicy {
	enum Confirmation { WAIT, STAND, STOP }
	static Confirmation placement(boolean pending, boolean dirt, int ticks) {
		if(ticks>160)return Confirmation.STOP;
		if(pending)return Confirmation.WAIT;
		if(dirt)return Confirmation.STAND;
		return ticks>=30?Confirmation.STOP:Confirmation.WAIT;
	}
	static boolean canRemove(boolean owned, boolean stillDirt, boolean underPlayer, boolean solidFloor, boolean dryFloor, boolean magma) {
		return owned && stillDirt && (!underPlayer || solidFloor && dryFloor && !magma);
	}
	static boolean shouldLift(double horizontal, boolean onSupport) { return horizontal <= (onSupport ? 3.8 : 2.8); }
	static boolean mustRelocate(double horizontal) { return horizontal>3.8; }
	static boolean canFinishTree(int remainingLogs,int supports) { return remainingLogs==0 && supports==0; }
}
