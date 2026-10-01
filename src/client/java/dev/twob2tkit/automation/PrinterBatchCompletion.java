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

    public void begin(Collection<K> targets){
        if(targets==null)throw new IllegalArgumentException("Printer completion targets are required");
        var checked=new HashSet<>(targets);
        if(checked.contains(null)||checked.size()!=targets.size())
            throw new IllegalArgumentException("Printer completion targets must be distinct and non-null");
        required=Set.copyOf(targets);confirmed.clear();
    }

    /** Another native action at this coordinate needs its own final-state ACK. */
    public void queued(K target){confirmed.remove(target);}

    /** Corrections to earlier targets still matter while a later action waits. */
    public void serverBlock(K target,V actual){
        if(confirmed.containsKey(target)&&!Objects.equals(confirmed.get(target),actual))
            confirmed.remove(target);
    }

    public void acknowledge(K target,V finalState,boolean travelAcknowledged,
                            boolean pacingAcknowledged,boolean exactFinalState){
        if(travelAcknowledged&&pacingAcknowledged&&exactFinalState&&finalState!=null
                &&required.contains(target))confirmed.put(target,finalState);
    }

    public boolean complete(Set<K> currentTargets){
        return !required.isEmpty()&&required.equals(currentTargets)&&confirmed.size()==required.size();
    }
}
