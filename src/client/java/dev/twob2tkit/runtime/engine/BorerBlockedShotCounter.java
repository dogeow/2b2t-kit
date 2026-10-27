package dev.twob2tkit.runtime.engine;

import java.util.List;

/** A blocked distant creeper must not starve an already-engaged incoming archer. */
final class BorerBlockedShotCounter {
    private long until=Long.MIN_VALUE;
    void blocked(boolean creeper,int consecutiveTicks,long tick){
        if(consecutiveTicks<10)return;
        // Keep this window across the target switch so the next tick cannot
        // cancel the counter-shot and select the same blocked creeper again.
        if(creeper)until=tick+100;
        else clear();
    }
    int choose(List<BorerDefensePolicy.Candidate> currentAttackable,int currentId,long tick){
        if(tick>=until)return -1;
        var shooters=currentAttackable.stream()
            .filter(c->c.priority()==1&&c.recentAttacker()).toList();
        return BorerDefensePolicy.choose(shooters,currentId);
    }
    void clear(){until=Long.MIN_VALUE;}
}
