package dev.twob2tkit.automation;

import java.util.Map;

/** Inventory evidence for one server-created map, never a reason to send another use. */
final class MapCreationPolicy {
    private MapCreationPolicy() {}

    static boolean canReceive(int heldEmptyMaps,int freeMainSlots) {
        return heldEmptyMaps>0 && (heldEmptyMaps==1 || freeMainSlots>0);
    }

    static int confirmedId(int emptyBefore,int emptyAfter,Map<Integer,Integer> before,
                           Map<Integer,Integer> after) {
        if(emptyBefore-emptyAfter!=1)return -1;
        int created=-1;
        for(var entry:before.entrySet())
            if(!entry.getValue().equals(after.get(entry.getKey())))return -1;
        for(var entry:after.entrySet()) {
            if(before.containsKey(entry.getKey()))continue;
            if(entry.getKey()<0 || entry.getValue()!=1 || created>=0)return -1;
            created=entry.getKey();
        }
        return created;
    }

    static int scaleZeroCenter(double coordinate) {
        if(!Double.isFinite(coordinate)||Math.abs(coordinate)>30_000_000)
            throw new IllegalArgumentException("Map creation coordinate is outside the world");
        return (int)Math.floor((coordinate+64)/128)*128;
    }
}
