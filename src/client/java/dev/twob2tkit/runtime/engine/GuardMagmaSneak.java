package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;

/** Packet Sneak protects a guarded magma approach without pressing Flight's descent key. */
final class GuardMagmaSneak {
    private final BorrowedPacketSneak lease=new BorrowedPacketSneak();
    private BorrowedPacketSneak.Access access;private String last="";
    private boolean nearby(Minecraft c){
        var box=c.player.getBoundingBox();
        for(int x=(int)Math.floor(box.minX+1e-7);x<=(int)Math.floor(box.maxX-1e-7);x++)
        for(int z=(int)Math.floor(box.minZ+1e-7);z<=(int)Math.floor(box.maxZ-1e-7);z++)
        for(int y=(int)Math.floor(c.player.getY());y>=(int)Math.floor(c.player.getY())-3;y--){
            var p=new BlockPos(x,y,z);if(!c.level.hasChunkAt(p))break;
            var state=c.level.getBlockState(p);if(state.is(Blocks.MAGMA_BLOCK))return true;
            if(state.getFluidState().isEmpty()&&state.isCollisionShapeFullBlock(c.level,p))break;
        }
        return false;
    }
    void tick(Minecraft c,boolean enabled){
        boolean wanted=enabled&&c.player!=null&&c.level!=null&&!c.player.isDeadOrDying()&&nearby(c);
        boolean eligible=false;
        try{if(wanted&&access==null)access=new MeteorAccess();eligible=lease.update(wanted,access);}
        catch(Exception unsupported){try{lease.close();}catch(Exception ignored){}}
        publish(c,wanted,eligible);
    }
    void close(Minecraft c){try{lease.close();}catch(Exception ignored){}publish(c,false,false);}
    private void publish(Minecraft c,boolean wanted,boolean eligible){
        String state=wanted+":"+eligible+":"+lease.owned();if(state.equals(last))return;last=state;
        try{
            var root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");Files.createDirectories(root);
            var j=new com.google.gson.JsonObject();j.addProperty("protocol",1);j.addProperty("time",System.currentTimeMillis());
            j.addProperty("runtime_version",EngineBuildVersion.VALUE);j.addProperty("hazard_scope_active",wanted);
            j.addProperty("packet_eligible",eligible);j.addProperty("owned",lease.owned());
            j.addProperty("recovery_confirmation",false);
            var target=root.resolve("guard-magma-sneak-state.json");var tmp=root.resolve("guard-magma-sneak-state.json.writing");
            Files.writeString(tmp,j.toString());Files.move(tmp,target,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }catch(Exception ignored){}
    }
    private static final class MeteorAccess implements BorrowedPacketSneak.Access {
        private final Object module,setting,packet;
        MeteorAccess()throws Exception{
            var classes=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            var modules=classes.getMethod("get").invoke(null);
            var type=Class.forName("meteordevelopment.meteorclient.systems.modules.movement.Sneak");
            module=classes.getMethod("get",Class.class).invoke(modules,type);
            var settings=type.getField("settings").get(module);setting=settings.getClass().getMethod("get",String.class).invoke(settings,"mode");
            Object value=mode();Object found=null;for(Object candidate:value.getClass().getEnumConstants())if(((Enum<?>)candidate).name().equals("Packet"))found=candidate;
            if(found==null)throw new IllegalStateException("Packet Sneak unavailable");packet=found;
        }
        public boolean active()throws Exception{return(Boolean)module.getClass().getMethod("isActive").invoke(module);}
        public Object mode()throws Exception{return setting.getClass().getMethod("get").invoke(setting);}
        public Object packet(){return packet;}
        public void mode(Object value)throws Exception{setting.getClass().getMethod("set",Object.class).invoke(setting,value);}
        public void active(boolean value)throws Exception{if(active()!=value)module.getClass().getMethod("toggle").invoke(module);if(active()!=value)throw new IllegalStateException("Sneak activation failed");}
        public boolean eligible()throws Exception{return(Boolean)module.getClass().getMethod("doPacket").invoke(module);}
    }
}
