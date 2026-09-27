package dev.twob2tkit.automation;

import java.util.List;

/** A material-dive budget. Ordinary swimming and mining retain their own limits. */
final class MaterialAirBudget {
    private MaterialAirBudget() {}

    record Sample(double climbed, int airUsed, long millis) {}
    record Estimate(int returnFloor, int pickupFloor, int workFloor, int estimatedLoss,
                    String source, int samples) {}

    static Estimate estimate(int maxAir, double climb, List<Sample> samples) {
        int full=Math.max(1,maxAir);
        int fallbackReturn=Math.min(full,240), fallbackWork=Math.min(full,260);
        if(samples==null || samples.size()<3 || !Double.isFinite(climb) || climb<0 || climb>40)
            return new Estimate(fallbackReturn,fallbackWork,fallbackWork,0,"fallback",samples==null?0:samples.size());
        double worstPerBlock=0,worstPerSecond=0;
        for(var sample:samples){
            if(sample==null || !Double.isFinite(sample.climbed()) || sample.climbed()<2
                    || sample.airUsed()<0 || sample.airUsed()>full
                    || sample.millis()<200 || sample.millis()>8000)
                return new Estimate(fallbackReturn,fallbackWork,fallbackWork,0,"fallback_bad_sample",samples.size());
            worstPerBlock=Math.max(worstPerBlock,sample.airUsed()/sample.climbed());
            worstPerSecond=Math.max(worstPerSecond,sample.airUsed()*1000.0/sample.millis());
        }
        int oneBubble=Math.max(1,(int)Math.ceil(full/10.0));
        int loss=(int)Math.ceil(worstPerBlock*climb);
        // At least 1.5 s of observed loss plus a fixed 15-air jitter reserve.
        // The one-bubble target is a lower bound, never a promise about arrival.
        int delay=Math.max(15,(int)Math.ceil(worstPerSecond*1.5));
        int returnFloor=Math.max(oneBubble+loss+delay,oneBubble+15);
        int pickupCost=Math.max(15,(int)Math.ceil(worstPerSecond*1.5)+8);
        int pickupFloor=returnFloor+pickupCost;
        int workCost=Math.max(pickupCost+10,(int)Math.ceil(worstPerSecond*2.5)+10);
        int workFloor=returnFloor+workCost;
        return new Estimate(returnFloor,pickupFloor,workFloor,loss,"observed",samples.size());
    }
}
