package dev.twob2tkit.automation;

import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Exact, distinct final-state packet receipts for one nonempty printer mask. */
public final class PrinterBatchCompletion<K,V> {
    private Set<K> required=Set.of();
    private final Map<K,V> confirmed=new HashMap<>();
    private record Passive<V>(V goal,V intermediate){}
    private final Map<K,Passive<V>> passive=new HashMap<>();

    public void begin(Collection<K> targets){
        if(targets==null)throw new IllegalArgumentException("Printer completion targets are required");
        var checked=new HashSet<>(targets);
        if(checked.contains(null)||checked.size()!=targets.size())
            throw new IllegalArgumentException("Printer completion targets must be distinct and non-null");
        required=Set.copyOf(targets);confirmed.clear();passive.clear();
    }

    /** Another native action at this coordinate needs its own final-state ACK. */
    public void queued(K target){confirmed.remove(target);passive.remove(target);}

    /** Corrections to earlier targets still matter while a later action waits. */
    public void serverBlock(K target,V actual){
        var follow=passive.get(target);
        if(follow!=null){
            if(Objects.equals(follow.goal(),actual))confirmed.put(target,follow.goal());
            else {confirmed.remove(target);if(!Objects.equals(follow.intermediate(),actual))passive.remove(target);}
            return;
        }
        if(confirmed.containsKey(target)&&!Objects.equals(confirmed.get(target),actual))
            confirmed.remove(target);
    }

    public void acknowledge(K target,V finalState,boolean travelAcknowledged,
                            boolean pacingAcknowledged,boolean exactFinalState){
        acknowledge(target,finalState,travelAcknowledged,pacingAcknowledged,exactFinalState,null);
    }
    /** Only an explicitly approved one-use passive state transition may finish without another use. */
    public void acknowledge(K target,V finalState,boolean travelAcknowledged,
                            boolean pacingAcknowledged,boolean exactFinalState,V passiveIntermediate){
        if(travelAcknowledged&&pacingAcknowledged&&exactFinalState&&finalState!=null
                &&required.contains(target))confirmed.put(target,finalState);
        else if(travelAcknowledged&&pacingAcknowledged&&!exactFinalState&&finalState!=null
                &&passiveIntermediate!=null&&!Objects.equals(passiveIntermediate,finalState)&&required.contains(target))
            passive.put(target,new Passive<>(finalState,passiveIntermediate));
    }

    public boolean complete(Set<K> currentTargets){
        return !required.isEmpty()&&required.equals(currentTargets)&&confirmed.size()==required.size();
    }
}
