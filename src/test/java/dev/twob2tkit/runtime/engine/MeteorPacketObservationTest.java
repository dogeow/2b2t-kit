package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class MeteorPacketObservationTest {
    public interface Listener {void call(Object event);Class<?> getTarget();int getPriority();boolean isStatic();}
    public static final class Event {}
    public static final class Attack {
        final java.util.UUID target;final boolean automatic;boolean cancelled;
        Attack(java.util.UUID target,boolean automatic){this.target=target;this.automatic=automatic;}
        public void setCancelled(boolean value){cancelled=value;}
    }
    public static final class Bus {
        final List<Listener> listeners=new ArrayList<>();int subscribed,unsubscribed;
        public void subscribe(Listener listener){listeners.add(listener);subscribed++;}
        public void unsubscribe(Listener listener){assertTrue(listeners.remove(listener));unsubscribed++;}
        void post(Object event){for(var listener:List.copyOf(listeners))if(listener.getTarget().isInstance(event))listener.call(event);}
    }
    @Test void reflected_listener_observes_without_changing_event_and_unsubscribes_once()throws Exception{
        var bus=new Bus();var received=new ArrayList<Object>();var event=new Event();
        var lease=MeteorPacketObservation.bind(bus,Listener.class,Event.class,received::add);
        assertEquals(1,bus.listeners.size());assertFalse(bus.listeners.getFirst().isStatic());
        assertEquals(Integer.MIN_VALUE,bus.listeners.getFirst().getPriority());
        bus.post(event);assertEquals(List.of(event),received);assertSame(event,received.getFirst());
        lease.close();lease.close();bus.post(new Event());assertEquals(1,received.size());assertEquals(1,bus.unsubscribed);
    }
    @Test void replacing_a_runtime_listener_does_not_keep_both_callbacks_registered()throws Exception{
        var bus=new Bus();var old=new AtomicInteger();var current=new AtomicInteger();
        var first=MeteorPacketObservation.bind(bus,Listener.class,Event.class,event->old.incrementAndGet());
        bus.post(new Event());first.close();
        try(var second=MeteorPacketObservation.bind(bus,Listener.class,Event.class,event->current.incrementAndGet())){
            bus.post(new Event());assertEquals(1,old.get());assertEquals(1,current.get());assertEquals(1,bus.listeners.size());
        }
        assertEquals(2,bus.subscribed);assertEquals(2,bus.unsubscribed);assertTrue(bus.listeners.isEmpty());
    }
    @Test void capture_veto_cancels_only_selected_automatic_attacks_and_is_removed_on_close()throws Exception{
        var bus=new Bus();var selected=java.util.UUID.randomUUID();
        try(var binding=MeteorPacketObservation.bind(bus,Listener.class,Attack.class,value->{
            var attack=(Attack)value;
            if(CaptureTargetPolicy.veto(selected,attack.target,attack.automatic,true,true))attack.setCancelled(true);
        })){
            var capture=new Attack(selected,true);bus.post(capture);assertTrue(capture.cancelled);
            var other=new Attack(java.util.UUID.randomUUID(),true);bus.post(other);assertFalse(other.cancelled);
            var manual=new Attack(selected,false);bus.post(manual);assertFalse(manual.cancelled);
        }
        var after=new Attack(selected,true);bus.post(after);assertFalse(after.cancelled);assertTrue(bus.listeners.isEmpty());
    }
}
