package dev.twob2tkit.automation;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/** Travel needs all observed placement actions confirmed, even when placement pacing is conservative. */
public final class PlacementTravelBarrier<K,V> {
    private record Pending<V>(V expected,boolean sent) {}
    private final Map<K,Pending<V>> pending=new HashMap<>();
    private boolean unknownAction;
    public void queued(K position,V expected){
        if(position==null||expected==null){unknownAction=true;return;}
        pending.put(position,new Pending<>(expected,false));
    }
    public void sent(K position){pending.computeIfPresent(position,(k,p)->new Pending<>(p.expected(),true));}
    public void serverBlock(K position,V actual){
        var p=pending.get(position);
        if(p!=null && p.sent() && Objects.equals(p.expected(),actual))pending.remove(position);
    }
    public void cancelUnsent(){pending.entrySet().removeIf(e->!e.getValue().sent());}
    public boolean settled(){return !unknownAction&&pending.isEmpty();}
    public int pendingCount(){return pending.size();}
}
