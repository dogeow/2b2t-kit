package dev.twob2tkit.combat;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import java.nio.file.*;
import java.util.*;

/** Early eating for owned work; restores the user's settings and keeps a crash-recovery receipt. */
public final class GuardFoodLease {
    private static final String AUTO_EAT="meteordevelopment.meteorclient.systems.modules.player.AutoEat";
    private record Borrowed(Object setting,Object original,Object written){}
    private static final List<Borrowed> borrowed=new ArrayList<>();
    private static Path path(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/guard-food-settings.bak.json");}
    private GuardFoodLease(){}
    private static Object module()throws Exception{
        var type=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
        return type.getMethod("get",Class.class).invoke(type.getMethod("get").invoke(null),Class.forName(AUTO_EAT));
    }
    private static Object setting(Object module,String name)throws Exception{var f=module.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(module);}
    private static Object read(Object setting)throws Exception{return setting.getClass().getMethod("get").invoke(setting);}
    private static void write(Object setting,Object value)throws Exception{
        Object accepted=setting.getClass().getMethod("set",Object.class).invoke(setting,value);
        if(Boolean.FALSE.equals(accepted)||!Objects.equals(read(setting),value))throw new IllegalStateException("AutoEat rejected the scoped setting");
    }
    private static Object decoded(JsonElement value,Object current){
        if(current instanceof Boolean)return value.getAsBoolean();
        if(current instanceof Integer)return value.getAsInt();
        if(current instanceof Double)return value.getAsDouble();
        if(current instanceof Enum<?> e)for(Object option:e.getDeclaringClass().getEnumConstants())if(((Enum<?>)option).name().equals(value.getAsString()))return option;
        throw new IllegalStateException("Unsupported AutoEat setting type");
    }
    public static void recover(Minecraft c){
        if(!borrowed.isEmpty()||!Files.exists(path(c)))return;
        try{recover(module(),path(c));}catch(Exception e){throw new IllegalStateException("Cannot restore prior AutoEat settings",e);}
    }
    static void recover(Object module,Path path){
        if(!borrowed.isEmpty()||!Files.exists(path))return;
        try{
            var record=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            for(var entry:record.entrySet()){
                Object option=setting(module,entry.getKey()),current=read(option);var values=entry.getValue().getAsJsonObject();
                Object previous=decoded(values.get("original"),current),written=decoded(values.get("written"),current);
                if(Objects.equals(current,written))write(option,previous);
            }
            Files.delete(path);
        }catch(Exception e){throw new IllegalStateException("Cannot restore prior AutoEat settings",e);}
    }
    public static void acquire(Minecraft c){
        if(!borrowed.isEmpty())return;
        try{acquire(module(),path(c));}catch(Exception e){throw new IllegalStateException("Cannot prepare early eating for unattended work",e);}
    }
    static void acquire(Object module,Path path){
        if(!borrowed.isEmpty())return;
        recover(module,path);
        try{
            if(module==null)throw new IllegalStateException("Meteor AutoEat unavailable");
            var record=new JsonObject();var planned=new ArrayList<Borrowed>();
            for(String name:List.of("thresholdMode","healthThreshold","hungerThreshold","searchInventory")){
                Object option=setting(module,name),original=read(option),value=switch(name){
                    case "healthThreshold"->19.0;case "hungerThreshold"->19;case "searchInventory"->true;
                    default->decoded(new JsonPrimitive("Any"),original);
                };
                var pair=new JsonObject();pair.add("original",new Gson().toJsonTree(original));pair.add("written",new Gson().toJsonTree(value));record.add(name,pair);planned.add(new Borrowed(option,original,value));
            }
            Files.createDirectories(path.getParent());Path tmp=path.resolveSibling(path.getFileName()+".tmp");
            Files.writeString(tmp,record.toString());Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
            for(var entry:planned){borrowed.add(entry);write(entry.setting(),entry.written());}
        }catch(Exception e){release();throw new IllegalStateException("Cannot prepare early eating for unattended work",e);}
    }
    public static void release(){
        for(var entry:borrowed)try{if(Objects.equals(read(entry.setting()),entry.written()))write(entry.setting(),entry.original());}catch(Exception ignored){}
        borrowed.clear();
    }
    public static JsonObject snapshot(){
        var j=new JsonObject();j.addProperty("owned",!borrowed.isEmpty());
        try{Object m=module();for(String name:List.of("thresholdMode","healthThreshold","hungerThreshold","searchInventory"))j.add(name,new Gson().toJsonTree(read(setting(m,name))));}
        catch(Exception e){j.addProperty("available",false);}return j;
    }
}
