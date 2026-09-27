package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;

/** Keeps calibration fresh between dives and stable during one bounded dive. */
final class MaterialAirCalibration {
    private static final long SAMPLE_TTL_MS=120000,MAX_DIVE_MS=120000;
    private final List<MaterialAirBudget.Sample> history=new ArrayList<>();
    private final List<Long> times=new ArrayList<>();
    private List<MaterialAirBudget.Sample> pinned=List.of();
    private String pinnedWorld="",pinnedJob="",pinnedGear="";
    private long pinnedUntil;

    void clearHistory(){history.clear();times.clear();clearDive();}
    void clearDive(){pinned=List.of();pinnedWorld="";pinnedJob="";pinnedGear="";pinnedUntil=0;}

    private void prune(long now){
        for(int i=times.size()-1;i>=0;i--)
            if(now-times.get(i)>SAMPLE_TTL_MS||times.get(i)>now+2000){
                times.remove(i);history.remove(i);
            }
    }

    void add(MaterialAirBudget.Sample sample,long now){
        prune(now);history.add(sample);times.add(now);
        if(history.size()>8){history.remove(0);times.remove(0);}
    }

    void enterDive(String world,String job,String gear,long now,int maxAir,double climb){
        if(isPinned(world,job,gear))return;
        clearDive();prune(now);
        if(MaterialAirBudget.estimate(maxAir,climb,history).source().equals("observed")){
            pinned=List.copyOf(history);pinnedWorld=world;pinnedJob=job;pinnedGear=gear;
            pinnedUntil=now+MAX_DIVE_MS;
        }
    }

    boolean isPinned(String world,String job,String gear){
        return !pinned.isEmpty()&&pinnedWorld.equals(world)
            &&pinnedJob.equals(job)&&pinnedGear.equals(gear);
    }

    List<MaterialAirBudget.Sample> samples(String world,String job,String gear,
                                           boolean underwater,long now){
        if(!pinned.isEmpty()&&!isPinned(world,job,gear)){
            clearDive();return List.of();
        }
        if(!underwater)clearDive();
        if(!pinned.isEmpty())return pinned;
        prune(now);return history;
    }

    long pinnedUntil(){return pinnedUntil;}
    boolean returnDue(String world,String job,String gear,long now){
        return isPinned(world,job,gear)&&now>=pinnedUntil-5000;
    }
}
