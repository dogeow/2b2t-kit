package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.world.phys.Vec3;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.function.Consumer;
import java.util.function.LongSupplier;
import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.platform.NativeImage;

/** Client-frame capture; GPU readback and PNG output are never desktop screenshots. */
public final class DecisionImageCapture {
    private static Pending pending;
    private static boolean inFlight;
    private record Pending(String id,String world,long revision,ClientLevel level,Vec3 pos,
                           LongSupplier currentRevision,Consumer<JsonObject> result,int ticks) {}
    private DecisionImageCapture() {}
    public static void request(Minecraft c,String id,String world,long revision,LongSupplier currentRevision,Consumer<JsonObject> result){
        if(pending!=null||inFlight)throw new IllegalStateException("A game image is already being captured");
        if(!DecisionImagePolicy.validId(id)||c.player==null||c.level==null||c.screen!=null)
            throw new IllegalStateException("Close the game interface before requesting a world image");
        pending=new Pending(id,world,revision,c.level,c.player.position(),currentRevision,result,2);
    }
    private static boolean valid(Minecraft c,Pending p){
        return DecisionImagePolicy.scope(c.level==p.level,c.player!=null,c.screen==null,p.revision,
            p.currentRevision.getAsLong(),c.player==null?Double.POSITIVE_INFINITY:c.player.position().distanceTo(p.pos));
    }
    private static JsonObject failure(String detail){var out=new JsonObject();out.addProperty("error",detail);return out;}
    public static void tick(Minecraft c){
        Pending p=pending;if(p==null)return;
        if(!valid(c,p)){pending=null;p.result.accept(failure("Game image context changed"));return;}
        if(p.ticks>0){pending=new Pending(p.id,p.world,p.revision,p.level,p.pos,p.currentRevision,p.result,p.ticks-1);return;}
        pending=null;
        try{
            long capturedAt=System.currentTimeMillis();
            inFlight=true;
            // Vanilla factors must divide BOTH framebuffer dimensions. Capture
            // at factor one and resize off-thread so arbitrary window sizes work.
            Screenshot.takeScreenshot(c.getMainRenderTarget(),1,image->c.execute(()->{
                if(!valid(c,p)){image.close();inFlight=false;p.result.accept(failure("Game image context changed during capture"));return;}
                CompletableFuture.runAsync(()->{var size=DecisionImagePolicy.boundedSize(image.getWidth(),image.getHeight());
                  try(image;var bounded=new NativeImage(size.width(),size.height(),false)){
                    image.resizeSubRectTo(0,0,image.getWidth(),image.getHeight(),bounded);
                    Path folder=c.gameDirectory.toPath().resolve("config/twob2tkit/automation/decision-images");
                    Files.createDirectories(folder);Path path=folder.resolve(p.id+".png");
                    if(Files.exists(path))throw new IllegalStateException("Image receipt already exists");
                    bounded.writeToFile(path.toFile());
                    var proof=new JsonObject();proof.addProperty("source","kit_framebuffer");
                    proof.addProperty("capture_id",p.id);proof.addProperty("path",path.toAbsolutePath().toString());
                    proof.addProperty("world_session",p.world);proof.addProperty("control_revision",p.revision);
                    proof.addProperty("captured_at",capturedAt);proof.addProperty("screen","");
                    proof.addProperty("width",bounded.getWidth());proof.addProperty("height",bounded.getHeight());
                    proof.addProperty("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))));
                    Files.writeString(folder.resolve(p.id+".json"),proof.toString());
                    c.execute(()->{inFlight=false;p.result.accept(valid(c,p)?proof:failure("Game image context changed before delivery"));});
                }catch(Exception e){c.execute(()->{inFlight=false;p.result.accept(failure("Native image capture failed: "+e.getClass().getSimpleName()));});}});
            }));
        }catch(Exception e){inFlight=false;p.result.accept(failure("Native image capture unavailable: "+e.getClass().getSimpleName()));}
    }
}
