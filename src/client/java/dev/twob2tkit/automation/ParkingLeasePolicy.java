package dev.twob2tkit.automation;

/** Lifecycle for a finished task that has already reached verified guarded high parking. */
final class ParkingLeasePolicy {
    enum Action { KEEP, REVOKE, LOGOUT }
    enum QuietWait { NONE, START, KEEP }
	record Anchor(double x,double y,double z) {}

    private ParkingLeasePolicy() {}

    static Action decide(String kind,boolean sameWorld,boolean sameRevision,
                         boolean manualMovement,boolean verifiedHighGuardPark) {
        if(!"parking".equals(kind)||!sameWorld||!sameRevision||manualMovement)
            return Action.REVOKE;
        return verifiedHighGuardPark?Action.KEEP:Action.LOGOUT;
    }

    /** Restore only an owned, dry high park whose sole missing condition is Flight. */
    static boolean recoverFlight(String kind, boolean sameWorld, boolean sameRevision,
                                 boolean manualMovement, boolean flightActive,
                                 boolean otherwiseVerifiedPark, boolean drySafeBody) {
        return "parking".equals(kind) && sameWorld && sameRevision && !manualMovement
            && !flightActive && otherwiseVerifiedPark && drySafeBody;
    }

    /** Safe stationary work sites can release a finished guard lease without disconnecting. */
    static boolean stayOnline(boolean same,boolean guardRequested,boolean manual,boolean lowHealth,
                              boolean guardArmed,boolean hostile,boolean bodySafe,boolean solidSupport,
                              boolean still,boolean screenClear,int food){
        return same&&guardRequested&&!manual&&!lowHealth&&guardArmed&&!hostile&&bodySafe
            &&solidSupport&&still&&screenClear&&food>=18;
    }

    /** A combat/quiet-window wait is still a closing material lease, never verified parking. */
    static QuietWait quietWait(boolean logoutRequested,boolean lowHealth,boolean quiet,
                               boolean alreadyWaiting) {
        if(!logoutRequested||lowHealth||quiet)return QuietWait.NONE;
        return alreadyWaiting?QuietWait.KEEP:QuietWait.START;
    }

	static Anchor reanchor(double x,double y,double z,int groundY,float health,
		boolean flightActive,boolean guardArmed){
		if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)
				||health<18||!flightActive||!guardArmed||y-groundY<18)return null;
		return new Anchor(x,Math.max(y,groundY+20.0),z);
	}

	static boolean guardRebase(String kind,boolean sameWorld,boolean sameRevision,
		boolean manualMovement,boolean pveOnly,boolean idle,boolean verifiedPark){
		return "parking".equals(kind)&&sameWorld&&sameRevision&&!manualMovement
			&&pveOnly&&idle&&verifiedPark;
	}
}
