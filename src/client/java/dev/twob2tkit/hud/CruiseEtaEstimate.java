package dev.twob2tkit.hud;

import java.util.ArrayDeque;

/** Remaining-time hint from recent observed progress, never from configured speed. */
public final class CruiseEtaEstimate {
    private record Sample(long time, double distance) {}
    private final ArrayDeque<Sample> samples = new ArrayDeque<>();
    private String route = "";
    private long lastProgress;

    public void clear() { samples.clear(); route = ""; lastProgress = 0; }

    public double observe(String identity, double distance, long now) {
        if (identity == null || identity.isBlank() || !Double.isFinite(distance) || distance < 0 || now < 0) {
            clear(); return -1;
        }
        var previous = samples.peekLast();
        if (!identity.equals(route) || previous != null &&
                (now < previous.time || now-previous.time > 2500 || distance > previous.distance+.25)) {
            clear(); route = identity; previous = null;
        }
        if (previous != null && now == previous.time) return estimate(distance, now);
        if (previous == null || distance < previous.distance-.01) lastProgress = now;
        samples.addLast(new Sample(now, distance));
        while (samples.size() > 1 && now-samples.peekFirst().time > 3000) samples.removeFirst();
        return estimate(distance, now);
    }

    private double estimate(double distance, long now) {
        if (samples.size() < 2 || now-lastProgress > 1000) return -1;
        var first = samples.peekFirst(); var last = samples.peekLast();
        double seconds = (last.time-first.time)/1000.;
        double progress = first.distance-last.distance;
        if (seconds < .5 || progress < .05) return -1;
        double rate = progress/seconds;
        return rate >= .1 ? Math.max(1, distance/rate) : -1;
    }
}
