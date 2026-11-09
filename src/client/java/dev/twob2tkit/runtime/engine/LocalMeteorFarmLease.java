package dev.twob2tkit.runtime.engine;
import java.util.*;
/** Temporary farm settings. Meteor owns all target selection and attack packets. */
final class LocalMeteorFarmLease implements AutoCloseable {
 private record Saved(Object setting,Object original,Object written){} private final List<Saved> saved=new ArrayList<>();private Object aura;
 private Object copy(Object v){return v instanceof Set<?> s?new LinkedHashSet<>(s):v;}
 private Object field(Object m,String name)throws ReflectiveOperationException{var f=m.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(m);}
 private Object get(Object s)throws ReflectiveOperationException{return s.getClass().getMethod("get").invoke(s);}
 private void set(Object s,Object v)throws ReflectiveOperationException{s.getClass().getMethod("set",Object.class).invoke(s,v);if(!Objects.equals(get(s),v))throw new IllegalStateException("Meteor rejected farm setting");}
 private void borrow(String name,Object value)throws ReflectiveOperationException{Object s=field(aura,name),old=copy(get(s));saved.add(new Saved(s,old,copy(value)));set(s,value);}
 boolean acquire(Object module,Object type){if(aura!=null)return ready();try{aura=module;borrow("entities",new LinkedHashSet<>(Set.of(type)));borrow("ignorePassive",false);borrow("onlyOnClick",false);borrow("onlyOnLook",false);borrow("range",3.0);borrow("wallsRange",3.0);borrow("maxTargets",1);borrow("customDelay",false);return ready();}catch(Exception e){close();return false;}}
 boolean ready(){if(aura==null)return false;try{if(!(Boolean)aura.getClass().getMethod("isActive").invoke(aura))return false;for(var v:saved)if(!Objects.equals(get(v.setting),v.written))return false;return true;}catch(Exception e){return false;}}
 Map<String,Object> observe(){var out=new LinkedHashMap<String,Object>();if(aura==null)return out;for(String n:List.of("ignorePassive","onlyOnClick","onlyOnLook","range","wallsRange","maxTargets","customDelay"))try{out.put(n,get(field(aura,n)));}catch(Exception e){}try{out.put("attacking",aura.getClass().getField("attacking").get(aura));}catch(Exception e){}return out;}
 @Override public void close(){for(var v:saved)try{if(Objects.equals(get(v.setting),v.written))set(v.setting,copy(v.original));}catch(Exception e){}saved.clear();aura=null;}
}
