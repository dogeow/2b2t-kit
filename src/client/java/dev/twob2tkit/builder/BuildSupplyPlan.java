package dev.twob2tkit.builder;
import java.util.*;
/** Resource arithmetic only; recorded stock never counts as a completed withdrawal. */
public final class BuildSupplyPlan {
    private BuildSupplyPlan(){}
    public static Map<String,Integer> targets(Map<String,Integer> needed,Map<String,Integer> carried){
        var result=new TreeMap<String,Integer>();
        needed.forEach((item,count)->{
            int missing=Math.max(0,count-carried.getOrDefault(item,0));
            if(missing==0)return;
            result.put(item,count);
            if(item.matches("minecraft:(oak|spruce|birch|jungle|acacia|dark_oak|mangrove|cherry|pale_oak)_planks")){
                String log=item.replace("_planks","_log");int logs=(missing+3)/4;
                if(carried.getOrDefault(log,0)<logs)result.put(log,logs);
            }
        });return result;
    }
    public static boolean confirmed(int inventoryBefore,int inventoryAfter,int sourceBefore,int sourceAfter,int expected){
        return expected>0 && inventoryAfter-inventoryBefore==expected && sourceBefore-sourceAfter==expected;
    }
}
