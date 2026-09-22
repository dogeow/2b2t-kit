package dev.twob2tkit.chopper;
/** An inaccessible replant site cannot turn a completed tree into an unfinished canopy. */
final class ChopperReplantPolicy {
 enum Blocked { DEFER_REPLANT, STOP_UNFINISHED_TREE }
 static Blocked blocked(int remainingLogs){return remainingLogs==0?Blocked.DEFER_REPLANT:Blocked.STOP_UNFINISHED_TREE;}
}
