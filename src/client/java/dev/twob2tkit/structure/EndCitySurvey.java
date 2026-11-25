package dev.twob2tkit.structure;

import java.util.ArrayDeque;
import java.util.List;

/** The candidate order is fixed when the player chooses a result. */
public final class EndCitySurvey {
    public enum Decision { WAIT, FOUND, NEXT, EXHAUSTED }
    public enum Observation { PENDING, NO_CITY, NO_SHULKERS, LIVE_SHULKER }
    public enum Position { SETTLING, IN_RANGE, RECENTER, LOST }

    private static final double CHECK_RADIUS = 24.0;
    private static final double MAX_RECENTER_DISTANCE = 96.0;
    private int recenterAttempts;
    private int steadyTicks;

    private final ArrayDeque<StructureLocator.Hit> candidates;
    private Observation previous;
    private int consecutive;

    public EndCitySurvey(List<StructureLocator.Hit> candidates) {
        this.candidates = new ArrayDeque<>(candidates);
    }

    public StructureLocator.Hit target() {
        return candidates.peekFirst();
    }

    public void beginArrival() {
        steadyTicks = 0;
        resetObservations();
    }

    /** Give the active Flight module time to coast before reading chunks or steering back. */
    public Position observePosition(double distance, double horizontalMovement) {
        if (!Double.isFinite(distance) || distance > MAX_RECENTER_DISTANCE) return Position.LOST;
        steadyTicks = horizontalMovement <= .2 ? steadyTicks + 1 : 0;
        if (steadyTicks < 4) return Position.SETTLING;
        if (distance <= CHECK_RADIUS) return Position.IN_RANGE;
        return ++recenterAttempts <= 3 ? Position.RECENTER : Position.LOST;
    }

    public void resetObservations() {
        consecutive = 0;
        previous = null;
    }

    /** Call every ten ticks while stationary at the observation point. */
    public Decision observe(Observation observation) {
        if (observation == Observation.LIVE_SHULKER) return Decision.FOUND;
        consecutive = previous == observation ? consecutive + 1 : 1;
        previous = observation;
        if (observation == Observation.NO_CITY && consecutive >= 2
                || observation == Observation.NO_SHULKERS && consecutive >= 8) {
            candidates.removeFirst();
            resetObservations();
            recenterAttempts = 0;
            return candidates.isEmpty() ? Decision.EXHAUSTED : Decision.NEXT;
        }
        return Decision.WAIT;
    }
}
