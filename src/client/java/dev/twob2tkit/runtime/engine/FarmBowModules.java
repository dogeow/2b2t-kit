package dev.twob2tkit.runtime.engine;
import java.util.*;
/** Borrow existing Meteor bow modules; never disables KillAura or AutoLog. */
final class FarmBowModules implements AutoCloseable {
 private record Saved(Object setting,Object original,Object written){}private final List<Saved> settings=new ArrayList<>();private final List<Object> enabled=new ArrayList<>();
 static Object module(String name)throws ReflectiveOperationException{var m=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");return m.getMethod("get",Class.class).invoke(m.getMethod("get").invoke(null),Class.forName("meteordevelopment.meteorclient.systems.modules.combat."+name));}
 static boolean active(Object m)throws ReflectiveOperationException{return m!=null&&(Boolean)m.getClass().getMethod("isActive").invoke(m);}
 static Object option(Object m,String n)throws ReflectiveOperationException{var f=m.getClass().getDeclaredField(n);f.setAccessible(true);return f.get(m);}
 static Object read(Object s)throws ReflectiveOperationException{return s.getClass().getMethod("get").invoke(s);}
 static Object copy(Object v){return v instanceof Set<?> s?new LinkedHashSet<>(s):v;}
 void borrow(Object m,String n,Object value)throws ReflectiveOperationException{Object o=option(m,n),old=copy(read(o));settings.add(new Saved(o,old,copy(value)));o.getClass().getMethod("set",Object.class).invoke(o,value);if(!Objects.equals(read(o),value))throw new IllegalStateException("Meteor rejected "+n);}
 void enable(Object m)throws ReflectiveOperationException{if(m==null)throw new IllegalStateException("Required Meteor module missing");if(!active(m)){enabled.add(m);m.getClass().getMethod("toggle").invoke(m);}if(!active(m))throw new IllegalStateException("Meteor bow module did not activate");}
 @SuppressWarnings({"rawtypes","unchecked"}) void begin(Object type)throws ReflectiveOperationException{Object aim=module("BowAimbot"),spam=module("BowSpam"),aura=module("KillAura");borrow(aura,"autoSwitch",false);borrow(aura,"pauseOnUse",true);borrow(aim,"entities",new LinkedHashSet<>(Set.of(type)));borrow(aim,"range",48.0);borrow(aim,"nametagged",false);Object priority=read(option(aim,"priority"));borrow(aim,"priority",Enum.valueOf((Class)priority.getClass(),"LowestDistance"));borrow(spam,"charge",20);borrow(spam,"onlyWhenHoldingRightClick",false);borrow(spam,"spamCrossbows",false);borrow(spam,"searchInventory",false);enable(aim);enable(spam);}
 boolean ready(){try{for(Object m:enabled)if(!active(m))return false;for(var s:settings)if(!Objects.equals(read(s.setting),s.written))return false;return true;}catch(Exception e){return false;}}
 public void close(){for(int i=enabled.size()-1;i>=0;i--)try{Object m=enabled.get(i);if(active(m))m.getClass().getMethod("toggle").invoke(m);}catch(Exception e){}enabled.clear();for(int i=settings.size()-1;i>=0;i--)try{var s=settings.get(i);if(Objects.equals(read(s.setting),s.written))s.setting.getClass().getMethod("set",Object.class).invoke(s.setting,copy(s.original));}catch(Exception e){}settings.clear();}
}
