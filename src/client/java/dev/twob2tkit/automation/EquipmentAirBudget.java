package dev.twob2tkit.automation;

/** Gear-based initial reserve. An ascent uses live air checks and later observed samples. */
final class EquipmentAirBudget {
    private EquipmentAirBudget() {}

    static double expectedSeconds(int air,double oxygenBonus){
        return Math.max(0,air)*(1+Math.max(0,oxygenBonus))/20.0;
    }

    static MaterialAirBudget.Estimate estimate(int maxAir,double climb,double oxygenBonus){
        if(!Double.isFinite(climb)||climb<0||climb>40||!Double.isFinite(oxygenBonus)||oxygenBonus<0)
            return MaterialAirBudget.estimate(maxAir,climb,null);
        int full=Math.max(1,maxAir);
        // Assume at most one block of climb per second until an observed ascent proves better.
        // Four seconds cover startup and network jitter. Air spending is probabilistic, so
        // Hoeffding's bound (p=1/(oxygen_bonus+1), failure probability <0.001) reserves
        // well above the mean rather than trusting the expected sixty seconds.
        int ticks=20*((int)Math.ceil(climb)+4);
        double chance=1/(oxygenBonus+1);
        int worst=(int)Math.ceil(ticks*chance+Math.sqrt(ticks*Math.log(1000)/2.0));
        int bubble=Math.max(1,(int)Math.ceil(full/10.0));
        int returnFloor=bubble+worst+15;
        int pickupFloor=returnFloor+Math.max(20,(int)Math.ceil(40*chance)+20);
        int workFloor=returnFloor+Math.max(40,(int)Math.ceil(70*chance)+35);
        return new MaterialAirBudget.Estimate(returnFloor,pickupFloor,workFloor,worst,"equipment",0);
    }
}
