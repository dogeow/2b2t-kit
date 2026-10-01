package dev.twob2tkit.automation;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

/** One excavation needs both a server target update and its native prediction ACK. */
final class SingleBlockServerConfirmation<K,V> {
    private record Claim<K>(String world, K target) {}
    private final Set<Claim<K>> uncertain = new HashSet<>();
    private Intent<K,V> current;

    private static final class Intent<K,V> {
        final String world, request;
        final K target;
        final Predicate<V> removed;
        int sentSequence=-1, ackSequence=-1;
        boolean localRemoval, serverUpdateSeen, serverRemoval;
        V serverState;
        Intent(String world,String request,K target,Predicate<V> removed) {
            this.world=world;this.request=request;this.target=target;this.removed=removed;
        }
    }

    void begin(String world,String request,K target,Predicate<V> removed) {
        if(world==null||world.isBlank()||request==null||request.isBlank()||target==null||removed==null)
            throw new IllegalArgumentException("Single-block confirmation requires current world, request and target");
        if(current!=null && current.world.equals(world))
            throw new IllegalStateException("Another single-block excavation is still active");
        if(uncertain.contains(new Claim<>(world,target)))
            throw new IllegalStateException("An earlier excavation at this target is unconfirmed; no retry sent");
        current=new Intent<>(world,request,target,removed);
    }

    void sent(String world,String request,K target,int sequence) {
        if(!matches(world,request,target)||sequence<0||sequence<current.sentSequence)
            throw new IllegalStateException("Native excavation no longer owns its prediction sequence");
        current.sentSequence=sequence;
        uncertain.add(new Claim<>(world,target));
    }

    /** Prediction only stops further sends; it never supplies completion evidence. */
    void clientState(String world,String request,K target,V actual) {
        if(matches(world,request,target)&&current.sentSequence>=0&&current.removed.test(actual))
            current.localRemoval=true;
    }

    void serverBlock(String world,String request,K target,V actual) {
        if(!matches(world,request,target)||current.sentSequence<0)return;
        current.serverUpdateSeen=true;current.serverState=actual;
        if(current.removed.test(actual))current.serverRemoval=true;
    }

    /** Acknowledgements contain no block state and cannot stand in for a block update. */
    void serverAck(String world,String request,K target,int sequence) {
        if(matches(world,request,target)&&current.sentSequence>=0)
            current.ackSequence=Math.max(current.ackSequence,sequence);
    }

    boolean hold(String world,String request,K target) {
        return matches(world,request,target)&&(current.localRemoval||current.serverRemoval);
    }

    boolean confirmed(String world,String request,K target,V clientState,boolean predictionPending) {
        return matches(world,request,target)&&current.sentSequence>=0
            &&current.serverUpdateSeen&&current.removed.test(current.serverState)
            &&current.ackSequence>=current.sentSequence&&!predictionPending
            &&Objects.equals(current.serverState,clientState);
    }

    boolean serverUpdateSeen(String world,String request,K target) {
        return matches(world,request,target)&&current.serverUpdateSeen;
    }
    V serverState(String world,String request,K target) {
        return serverUpdateSeen(world,request,target)?current.serverState:null;
    }
    int sentSequence(String world,String request,K target) {
        return matches(world,request,target)?current.sentSequence:-1;
    }
    int ackSequence(String world,String request,K target) {
        return matches(world,request,target)?current.ackSequence:-1;
    }

    /** Unknown outcomes keep their target claim even after the owner releases its inputs. */
    void close(String request,boolean confirmed) {
        if(current==null||!current.request.equals(request))return;
        if(confirmed||current.sentSequence<0)uncertain.remove(new Claim<>(current.world,current.target));
        current=null;
    }

    private boolean matches(String world,String request,K target) {
        return current!=null&&current.world.equals(world)&&current.request.equals(request)
            &&current.target.equals(target);
    }
}
