package dev.twob2tkit.automation;

/** Pure gate: only one exact host-permitted material snow cruise may move guard scope. */
final class SnowGuardScopePolicy {
	private SnowGuardScopePolicy() {}
	static boolean rebase(boolean active,boolean navigate,boolean token,
		boolean currentMaterialLease,boolean currentPermit,
		boolean pveOnly,boolean controllerActive){
		return active&&navigate&&token&&currentMaterialLease&&currentPermit
			&&pveOnly&&controllerActive;
	}
	static boolean pendingReturn(boolean navigate,boolean token,
		boolean currentMaterialLease,boolean pveOnly,boolean currentPermit){
		return navigate&&token&&currentMaterialLease&&pveOnly&&currentPermit;
	}
	static boolean inFlight(boolean active,boolean navigate,boolean token,
		boolean currentMaterialLease,boolean pveOnly,boolean currentPermit){
		return active&&navigate&&token&&currentMaterialLease&&pveOnly&&currentPermit;
	}
}
