package dev.twob2tkit.automation;

/** Pure safety policy for one explicitly observed construction-blocking horse. */
public final class HorseNudgePolicy {
    public static final double BLOCKER_RADIUS = 4.0;
    public static final double REQUIRED_CLEARANCE = 6.0;
    public static final double ESCAPE_RESERVE = 6.5;
    public static final double POSITION_TOLERANCE = .35;
    public static final double MAX_EMPTY_HAND_DAMAGE = 1.0;
    public static final float MIN_HORSE_HEALTH = 8.0F;
    public static final long MAX_OBSERVATION_AGE_MS = 3_000;

    public enum Outcome { RUNNING, DONE, WAITING }
    public record Point(double x,double y,double z) {}

    private HorseNudgePolicy() {}

    public static boolean scopeValid(String requestWorld,String currentWorld,long requestRevision,
                                     long currentRevision,long expiresAt,long observedAt,long now) {
        long lifetime=expiresAt-now, age=now-observedAt;
        return requestWorld!=null&&requestWorld.equals(currentWorld)
            &&requestRevision==currentRevision&&lifetime>=0&&lifetime<=15_000
            &&age>=0&&age<=MAX_OBSERVATION_AGE_MS;
    }

    public static boolean exactObservation(Point expected,Point actual,float expectedHealth,
                                           float actualHealth) {
        return finite(expected)&&finite(actual)&&Float.isFinite(expectedHealth)&&Float.isFinite(actualHealth)
            &&distance(expected,actual)<=POSITION_TOLERANCE
            &&Math.abs(expectedHealth-actualHealth)<=.01F;
    }

    public static boolean safeEmptyHandHit(float horseHealth,double attackDamage,boolean emptyHand,
                                           boolean playerOnGround,double fallDistance,
                                           boolean sprinting,float attackStrength) {
        return Float.isFinite(horseHealth)&&Double.isFinite(attackDamage)&&Double.isFinite(fallDistance)
            &&horseHealth>=MIN_HORSE_HEALTH&&attackDamage>=0&&attackDamage<=MAX_EMPTY_HAND_DAMAGE
            &&emptyHand&&playerOnGround&&fallDistance<=.01&&!sprinting&&attackStrength>=.95F;
    }

    public static String geometryRejection(Point protectedCell,Point horse,Point player,Point escape,
                                           double interactionRange) {
        if(!finite(protectedCell)||!finite(horse)||!finite(player)||!finite(escape)
                ||!Double.isFinite(interactionRange))return "Horse nudge coordinates are invalid";
        double initial=horizontal(horse,protectedCell), destination=horizontal(escape,protectedCell);
        if(initial>BLOCKER_RADIUS)return "Horse is not the explicit construction blocker";
        if(destination<ESCAPE_RESERVE)return "Escape target does not leave the protected clearance";
        if(Math.abs(escape.y-horse.y)>.75)return "Escape target changes horse elevation";
        double ex=escape.x-horse.x,ez=escape.z-horse.z,travel=Math.hypot(ex,ez);
        double kx=horse.x-player.x,kz=horse.z-player.z,reach=Math.hypot(kx,kz);
        if(travel<1||travel>12)return "Escape target distance is outside the one-hit check";
        if(reach<1||reach>interactionRange-.2)return "Player is not in a safe attack pose";
        double alignment=(ex*kx+ez*kz)/(travel*reach);
        if(alignment<.92)return "Player is not behind the horse along the verified escape direction";
        double previous=initial;
        for(double step=.5;step<travel;step+=.5){
            Point sample=new Point(horse.x+ex*step/travel,horse.y,horse.z+ez*step/travel);
            double current=horizontal(sample,protectedCell);
            if(current+.01<previous)return "Escape path turns toward the protected construction cell";
            previous=current;
        }
        return null;
    }

    public static Outcome outcome(boolean exactHorse,boolean alive,float health,
                                  double clearanceDistance,boolean timedOut) {
        if(exactHorse&&(!alive||!Float.isFinite(health)||health<=0))return Outcome.WAITING;
        if(exactHorse&&alive&&health>0&&Double.isFinite(clearanceDistance)
                &&clearanceDistance>=REQUIRED_CLEARANCE)return Outcome.DONE;
        return timedOut?Outcome.WAITING:Outcome.RUNNING;
    }

    public static double horizontal(Point a,Point b){return Math.hypot(a.x-b.x,a.z-b.z);}
    private static double distance(Point a,Point b){return Math.sqrt(
        (a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y)+(a.z-b.z)*(a.z-b.z));}
    private static boolean finite(Point p){return p!=null&&Double.isFinite(p.x)&&Double.isFinite(p.y)&&Double.isFinite(p.z);}
}
