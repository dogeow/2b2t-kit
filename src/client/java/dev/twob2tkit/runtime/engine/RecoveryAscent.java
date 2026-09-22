package dev.twob2tkit.runtime.engine;

import com.google.gson.*;
import java.nio.file.*;
import net.minecraft.client.Minecraft;
import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;

/** Explicit, expiring local recovery command. Uses normal Flight and Jump, never teleports. */
final class RecoveryAscent {
    private String lastId="";private JsonObject command;private int polls;
    private Path path(Minecraft c,String name){return c.gameDirectory.toPath().resolve("config/twob2tkit/"+name);}
    static boolean inScope(double x,double y,double z,double sx,double sy,double sz,double target,long expires,long now){
        return Double.isFinite(target)&&Math.hypot(x-sx,z-sz)<=2&&Math.abs(y-sy)<=2&&target>sy&&target<=sy+12&&expires>now&&expires-now<=180000;
    }
    boolean tick(Minecraft c){
        if(c.player==null||c.level==null)return false;
        if(command==null && ++polls%5==0){
            try{
                Path p=path(c,"recovery-ascent.json");if(!Files.isRegularFile(p)||Files.size(p)>2048)return false;
                JsonObject j=JsonParser.parseString(Files.readString(p)).getAsJsonObject();String id=j.get("id").getAsString();if(id.equals(lastId))return false;
                String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
                if(!server.equals(j.get("server").getAsString()) || !c.level.dimension().identifier().toString().equals(j.get("dimension").getAsString()))return false;
                var a=j.getAsJsonArray("start");long expiry=j.get("expires").getAsLong();
                if(!inScope(c.player.getX(),c.player.getY(),c.player.getZ(),a.get(0).getAsDouble(),a.get(1).getAsDouble(),a.get(2).getAsDouble(),j.get("target_y").getAsDouble(),expiry,System.currentTimeMillis()))return false;
                if(c.screen!=null&&!c.screen.getClass().getSimpleName().equals("LevelLoadingScreen"))return false;
                lastId=id;command=j;result(c,"running");
            }catch(Exception bad){return false;}
        }
        if(command==null)return false;
        var anchor=command.getAsJsonArray("start");
        String currentServer=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
        if(!currentServer.equals(command.get("server").getAsString()) || !c.level.dimension().identifier().toString().equals(command.get("dimension").getAsString()) || Math.hypot(c.player.getX()-anchor.get(0).getAsDouble(),c.player.getZ()-anchor.get(2).getAsDouble())>2){cancel(c,"context_changed");return false;}
        if(c.screen!=null&&!c.screen.getClass().getSimpleName().equals("LevelLoadingScreen")||c.player.isDeadOrDying()||System.currentTimeMillis()>=command.get("expires").getAsLong()){cancel(c,"cancelled");return false;}
        for(var key:new net.minecraft.client.KeyMapping[]{c.options.keyUp,c.options.keyDown,c.options.keyLeft,c.options.keyRight,c.options.keyJump,c.options.keyShift}){
            var bound=KeyMappingHelper.getBoundKeyOf(key);
            if(c.isWindowActive()&&bound.getType()==InputConstants.Type.KEYSYM&&InputConstants.isKeyDown(c.getWindow(),bound.getValue())){cancel(c,"manual_takeover");return false;}
        }
        if(!c.level.hasChunkAt(c.player.blockPosition().above()))return false;
        if(c.player.getY()>=command.get("target_y").getAsDouble()-.1){cancel(c,"done");return false;}
        if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(0,.55,0))){cancel(c,"ceiling_blocked");return false;}
        if(!BorerFlight.ensureFlying(c.player,true)){cancel(c,"flight_unavailable");return false;}
        c.options.keyUp.setDown(false);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyShift.setDown(false);c.options.keyJump.setDown(true);
        return true;
    }
    void cancel(Minecraft c,String why){if(command==null)return;c.options.keyJump.setDown(false);result(c,why);command=null;}
    private void result(Minecraft c,String status){
        try{JsonObject j=new JsonObject();j.addProperty("id",lastId);j.addProperty("status",status);j.addProperty("time",System.currentTimeMillis());if(c.player!=null){j.addProperty("y",c.player.getY());j.addProperty("health",c.player.getHealth());}Files.writeString(path(c,"recovery-ascent-result.json"),j.toString());}catch(Exception ignored){}
    }
}
