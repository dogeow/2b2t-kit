package dev.twob2tkit.builder;
/** Ordinary task completion waits for quiet. It does not change emergency low-health policy. */
public final class QuietLogoutWindow {
 private long lastDanger;
 public void reset(long now){lastDanger=now;}
 public boolean ready(long now,boolean defendingOrThreatened,long lastHurt){
  if(defendingOrThreatened)lastDanger=now;
  return now-Math.max(lastDanger,lastHurt)>=60_000;
 }
}
