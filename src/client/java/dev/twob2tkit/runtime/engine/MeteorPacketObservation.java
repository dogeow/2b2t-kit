package dev.twob2tkit.runtime.engine;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.function.Consumer;

/** Optional incoming-packet observer. It never sends or cancels a packet. */
final class MeteorPacketObservation implements AutoCloseable {
    record Incoming(Object packet,Object connection) {}
    private Object bus,listener;
    private Method unsubscribe;

    static MeteorPacketObservation open(Consumer<Incoming> receive) throws ReflectiveOperationException {
        Class<?> meteor=Class.forName("meteordevelopment.meteorclient.MeteorClient");
        Class<?> listenerType=Class.forName("meteordevelopment.orbit.listeners.IListener");
        Class<?> eventType=Class.forName("meteordevelopment.meteorclient.events.packets.PacketEvent$Receive");
        var packet=eventType.getField("packet");var connection=eventType.getField("connection");
        return bind(meteor.getField("EVENT_BUS").get(null),listenerType,eventType,event->{
            try { receive.accept(new Incoming(packet.get(event),connection.get(event))); }
            catch(ReflectiveOperationException ignored) { /* A missing observation authorizes nothing. */ }
        });
    }

    static MeteorPacketObservation bind(Object bus,Class<?> listenerType,Class<?> eventType,Consumer<Object> receive)
            throws ReflectiveOperationException {
        var result=new MeteorPacketObservation();
        Object listener=Proxy.newProxyInstance(listenerType.getClassLoader(),new Class<?>[]{listenerType},(proxy,method,args)->switch(method.getName()) {
            case "getTarget" -> eventType;
            case "getPriority" -> Integer.MIN_VALUE;
            case "isStatic" -> false;
            case "call" -> { receive.accept(args[0]);yield null; }
            case "hashCode" -> System.identityHashCode(proxy);
            case "equals" -> proxy==args[0];
            case "toString" -> "Kit incoming packet observation";
            default -> throw new UnsupportedOperationException("Unsupported incoming listener method");
        });
        result.unsubscribe=bus.getClass().getMethod("unsubscribe",listenerType);
        bus.getClass().getMethod("subscribe",listenerType).invoke(bus,listener);
        result.bus=bus;result.listener=listener;return result;
    }

    @Override public void close() {
        if(listener==null)return;
        try { unsubscribe.invoke(bus,listener); }
        catch(ReflectiveOperationException ignored) { /* The callback epoch is also invalidated by the owner. */ }
        finally { listener=null;bus=null;unsubscribe=null; }
    }
}
