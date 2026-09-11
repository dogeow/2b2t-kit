package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.*;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.Vec3;
import java.nio.file.*;
import java.util.*;

/** Local, opt-in job files. All game actions execute on the client tick and use normal interactions. */
public final class AutomationBridge {
    private static final Gson JSON=new GsonBuilder().disableHtmlEscaping().create();
    private static String lastId="", statusId="", phase="idle", detail="", op="";
    private static JsonObject active;
    private static int ticks, deadline, desiredCount;
    private static JsonObject guardScope;
    private static boolean guardBusy;
    public static boolean guardBusy(){return guardBusy;}
    public static boolean guardArmed(){return guardScope!=null;}
    /** Stop is an explicit operation, never inferred from translated reason text. */
    public static void disarmGuard(Minecraft c){
        guardScope=null;guardBusy=false;
        if(KitClient.borer()!=null)KitClient.borer().tickStandaloneGuard(c,false);
    }
    public static boolean yieldGuardToManualInput(Minecraft c){
        if(!guardArmed() || !KitKeys.manualMovementDown(c))return false;
        KitClient.emergencyStop("手动移动接管");
        return true;
    }
    public static void toggleGuard(Minecraft c){
        if(guardArmed()){KitClient.emergencyStop("手动关闭独立防护");return;}
        armCurrentGuard(c);
    }
    public static void armCurrentGuard(Minecraft c){
        if(c.player==null || c.level==null || c.player.isDeadOrDying())return;
        guardScope=new JsonObject();guardScope.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);
        guardScope.addProperty("dimension",c.level.dimension().identifier().toString());
        guardScope.add("site",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));
        MeteorModules.enable(MeteorModules.KILL_AURA);MeteorModules.enable(MeteorModules.AUTO_LOG);
    }
    public static boolean beforeGuard(Minecraft c){
        boolean enabled=guardScope!=null;
        if(enabled)try{guard(c,guardScope);}catch(Exception changed){guardScope=null;enabled=false;}
        guardBusy=KitClient.borer().tickStandaloneGuard(c,enabled);
        if(guardBusy){ProfessionalPrinter.pause();if(active!=null)deadline++;mineStarted=false;}
        return guardBusy;
    }
    private static double savedArrival=Double.NaN, temporaryArrival;
    private static boolean restoreFlight;
    private static boolean mineStarted;
    private static boolean guiRequested, initialized;
    private static Path root(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/automation");}
    public static void requestGui(){guiRequested=true;}
    public static boolean ownsMining(){return active!=null && op.equals("mine_block");}
    public static void cancel(Minecraft c,String reason){
        disarmGuard(c);
        cancelWork(c,reason);
    }
    public static void cancelWork(Minecraft c,String reason){
        ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);
        active=null;phase="stopped";detail=reason;writeStatus(c);
    }
    /** Short-range walking owns input before Minecraft samples keys; it does not use cruise fly-over routing. */
    public static boolean beforeInput(Minecraft c){
        if(active==null || !Set.of("walk","mine_block").contains(op) || c.player==null || c.level==null)return false;
        if(c.screen!=null){c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyAttack.setDown(false);return true;}
        if(op.equals("mine_block")){
            try{guard(c,active);}catch(Exception e){finish(c,"stopped",e.getMessage());return true;}
            JsonArray a=active.getAsJsonArray("pos");BlockPos target=new BlockPos(a.get(0).getAsInt(),a.get(1).getAsInt(),a.get(2).getAsInt());
            if(c.level.isEmptyBlock(target)){finish(c,"done","target removed");return true;}
            if(!state(c,target).equals(str(active,"expected_state"))){finish(c,"error","mining target changed");return true;}
            Vec3 aim=Vec3.atCenterOf(target);if(c.player.getEyePosition().distanceTo(aim)>c.player.blockInteractionRange()-.2){finish(c,"waiting","mining target moved out of reach");return true;}RotationAim.Look look=RotationAim.lookAt(c.player,aim);RotationAim.apply(c.player,look);
            BlockHitResult hit=c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(!hit.getBlockPos().equals(target)){finish(c,"waiting","mining target is occluded");return true;}
            c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keyAttack.setDown(false);c.hitResult=hit;
            if(!mineStarted){c.gameMode.startDestroyBlock(target,hit.getDirection());mineStarted=true;}
            else c.gameMode.continueDestroyBlock(target,hit.getDirection());
            return true;
        }
        JsonArray p=active.getAsJsonArray("target");double dx=p.get(0).getAsDouble()-c.player.getX(),dz=p.get(2).getAsDouble()-c.player.getZ();
        double distance=Math.hypot(dx,dz),arrival=active.has("arrival")?active.get("arrival").getAsDouble():.65;
        if(c.player.onGround() && distance>arrival){
            BlockPos foot=BlockPos.containing(c.player.getX()+dx/distance*.7,c.player.getY()-.1,c.player.getZ()+dz/distance*.7);boolean supported=false;
            for(int down=0;down<3;down++){BlockPos q=foot.below(down);if(!c.level.getBlockState(q).getCollisionShape(c.level,q).isEmpty()){supported=true;break;}}
            if(!supported){finish(c,"waiting","unsafe drop ahead; choose another walking waypoint");return true;}
        }
        RotationAim.apply(c.player,RotationAim.yawToward(dx,dz),10);
        c.options.keyUp.setDown(distance>arrival);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyShift.setDown(false);
        double dy=p.get(1).getAsDouble()-c.player.getY();c.options.keyJump.setDown(c.player.onGround() && dy>.5 && dy<1.3);
        return true;
    }
    private static void releaseWalk(Minecraft c){if(!Set.of("walk","mine_block").contains(op))return;if(c.options!=null){c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keyAttack.setDown(false);}if(op.equals("mine_block") && c.gameMode!=null)c.gameMode.stopDestroyBlock();if(restoreFlight){MeteorModules.enable(MeteorModules.FLIGHT);restoreFlight=false;}}
    public static void tick(Minecraft c){
        if(!initialized){initialized=true;try{Path old=root(c).resolve("request.json");if(Files.isRegularFile(old))lastId=str(JsonParser.parseString(Files.readString(old)).getAsJsonObject(),"id");}catch(Exception ignored){}}
        if(guiRequested){guiRequested=false;if(c.player!=null)KitClient.openGui(c);}
        ticks++;
        if(ticks%5==0){
            Path f=root(c).resolve("request.json");
            try{
                if(Files.isRegularFile(f) && Files.size(f)<=16384){
                    JsonObject r=JsonParser.parseString(Files.readString(f)).getAsJsonObject();String id=str(r,"id");
                    if(!id.isBlank() && !id.equals(lastId)){
                        lastId=id;
                        try {
                            if(active!=null && !str(r,"op").equals("stop") && !Set.of("snapshot","scan").contains(str(r,"op")))throw new IllegalStateException("A job is active; stop it first");
                            dispatch(c,r);
                        } catch(Exception e) {
                            if(active!=null && str(active,"id").equals(id)){KitClient.emergencyStop("脚本参数无效");active=null;}
                            JsonObject error=snapshot(c);error.addProperty("id",id);error.addProperty("phase","error");error.addProperty("detail",e.getMessage());save(root(c).resolve("reply-"+safeId(id)+".json"),error);
                            if(active==null){statusId=id;phase="error";detail=e.getMessage();writeStatus(c);}
                        }
                    }
                }
            }catch(Exception e){phase="error";detail=e.getClass().getSimpleName()+": "+e.getMessage();writeStatus(c);}
        }
        if(active!=null){
            try{
                guard(c,active);
                if(op.equals("professional_print")){
                    if(!ProfessionalPrinter.failure().isEmpty()){finish(c,"error",ProfessionalPrinter.failure());return;}
                    if(!guardBusy && c.screen==null && c.player.getHealth()>=14)ProfessionalPrinter.resume();
                    if(!guardBusy && (c.player.getHealth()<14 || !MeteorModules.isActive(MeteorModules.KILL_AURA) || !MeteorModules.isActive(MeteorModules.AUTO_LOG))){finish(c,"waiting","health or defense requires attention");}
                    else if(ticks>=deadline)finish(c,"done","printer interval ended; verify actual block states");
                }else if(op.equals("mine_block")){
                    JsonArray p=active.getAsJsonArray("pos");BlockPos target=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());if(c.level.isEmptyBlock(target))finish(c,"done","target removed");
                }else if(op.equals("walk")){
                    JsonArray p=active.getAsJsonArray("target");double dx=c.player.getX()-p.get(0).getAsDouble(),dz=c.player.getZ()-p.get(2).getAsDouble();
                    double arrival=active.has("arrival")?active.get("arrival").getAsDouble():.65;
                    if(Math.hypot(dx,dz)<=arrival && Math.abs(c.player.getY()-p.get(1).getAsDouble())<=1.2)finish(c,"done","walk target reached");
                }else if(op.equals("chop")){
                    if(count(c,str(active,"item"))>=desiredCount){KitClient.chopper().stop(c,"已达到脚本材料目标");finish(c,"done","material target reached");}
                    else if(!KitClient.chopper().isActive())finish(c,"stopped","chopper stopped");
                }else if(op.equals("navigate") && !KitClient.controller().isActive()){
                    JsonArray p=active.getAsJsonArray("target");double dx=c.player.getX()-p.get(0).getAsDouble(),dz=c.player.getZ()-p.get(2).getAsDouble();
                    finish(c,Math.hypot(dx,dz)<=KitClient.config().arrivalRadius+1 && Math.abs(c.player.getY()-p.get(1).getAsDouble())<=1?"done":"stopped","navigation ended");
                }else if(op.equals("print") && !KitClient.machines().isPlacing())finish(c,"stopped","printer stopped");
                else if(op.equals("settle") && ticks>=deadline)finish(c,"done","server state available");
                if(active!=null && ticks>=deadline && !op.equals("settle")){
                    KitClient.emergencyStop("脚本任务达到时间上限");finish(c,"waiting","time limit reached; inspect progress before resuming");
                }
            }catch(Exception e){KitClient.emergencyStop("脚本世界或人物状态已变化");finish(c,"stopped",e.getMessage());}
        }
        ProfessionalPrinter.tick(c);
        if(ticks%20==0)writeStatus(c);
    }
    private static void guard(Minecraft c,JsonObject r){
        if(c.player==null || c.level==null || c.gameMode==null || c.player.isDeadOrDying())throw new IllegalStateException("Not alive in a world");
        String current=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
        if(!AutomationScope.sameServer(current,str(r,"server")))throw new IllegalStateException("Wrong server");
        if(!c.level.dimension().identifier().toString().equals(str(r,"dimension")))throw new IllegalStateException("Wrong dimension");
        JsonArray site=r.getAsJsonArray("site");
        if(site==null || site.size()!=3)throw new IllegalArgumentException("Site is required");
        double dx=c.player.getX()-site.get(0).getAsDouble(),dz=c.player.getZ()-site.get(2).getAsDouble();
        if(!AutomationScope.nearSite(dx,dz))throw new IllegalStateException("Outside authorized worksite; lobby actions refused");
    }
    private static void dispatch(Minecraft c,JsonObject r)throws Exception{
        String command=str(r,"op");
        if(command.equals("stop")){statusId=lastId;ProfessionalPrinter.stop(c,true);KitClient.emergencyStop("本地脚本停止");active=null;phase="stopped";detail="stopped";writeStatus(c);return;}
        guard(c,r);
        if(Set.of("snapshot","scan").contains(command)){
            JsonObject out=snapshot(c);out.addProperty("id",lastId);
            if(command.equals("scan"))out.add("blocks",scan(c,r));
            save(root(c).resolve("reply-"+safeId(lastId)+".json"),out);writeStatus(c);return;
        }
        if(guardBusy && !command.equals("guard"))throw new IllegalStateException("Construction guard is defending or eating; wait before changing items or starting work");
        statusId=lastId;
        if(command.equals("professional_print")){
            KitClient.stopWork("使用投影打印机");
            if(c.player.getHealth()<14 || !MeteorModules.isActive(MeteorModules.KILL_AURA) || !MeteorModules.isActive(MeteorModules.AUTO_LOG))throw new IllegalStateException("Health or defense requires attention");
            ProfessionalPrinter.start(!r.has("conservative") || !r.get("conservative").getAsBoolean());active=r.deepCopy();op=command;phase="running";detail="Litematica Printer owns placement";
            deadline=ticks+20*Math.max(1,Math.min(30,r.has("seconds")?r.get("seconds").getAsInt():10));
        }else if(command.equals("navigate") || command.equals("walk") || command.equals("chop") || command.equals("print")){
            ProfessionalPrinter.stop(c,true);KitClient.stopWork("切换到脚本任务");active=r.deepCopy();op=command;phase="running";detail="";
            deadline=ticks+20*Math.max(5,Math.min(600,r.has("seconds")?r.get("seconds").getAsInt():120));
            if(command.equals("walk")){
                JsonArray p=r.getAsJsonArray("target");checkSiteTarget(r,p);
                double d=Math.hypot(p.get(0).getAsDouble()-c.player.getX(),p.get(2).getAsDouble()-c.player.getZ());if(d>32)throw new IllegalArgumentException("Walking waypoint must be within 32 blocks");
                restoreFlight=MeteorModules.isActive(MeteorModules.FLIGHT) && (!r.has("restore_flight") || r.get("restore_flight").getAsBoolean());MeteorModules.disable(MeteorModules.FLIGHT);
            }else if(command.equals("navigate")){
                JsonArray p=r.getAsJsonArray("target");checkSiteTarget(r,p);
                if(r.has("arrival")){savedArrival=KitClient.config().arrivalRadius;temporaryArrival=Math.max(1,Math.min(8,r.get("arrival").getAsDouble()));KitClient.config().arrivalRadius=temporaryArrival;}
                MeteorModules.enable(MeteorModules.FLIGHT);
                KitClient.controller().startExact(c,p.get(0).getAsDouble(),p.get(2).getAsDouble(),p.get(1).getAsDouble());
            }else if(command.equals("chop")){
                if(!r.has("item"))active.addProperty("item","minecraft:oak_log");
                desiredCount=Math.max(1,Math.min(512,r.get("target_count").getAsInt()));KitClient.chopper().start(c);
            }else if(!KitClient.machines().start(c))throw new IllegalStateException("Could not start printer");
        }else if(command.equals("guard")){
            guardScope=r.deepCopy();
            MeteorModules.enable(MeteorModules.KILL_AURA);MeteorModules.enable(MeteorModules.AUTO_LOG);
            MeteorModules.enable("meteordevelopment.meteorclient.systems.modules.player.AutoEat");
            phase="done";detail="guard modules enabled";
        }else if(command.equals("look")){
            PlacementRotation.after(c,r.get("yaw").getAsFloat(),Math.max(-90,Math.min(90,r.get("pitch").getAsFloat())),null);phase="done";detail="rotation queued";
        }else if(command.equals("select_item")){
            if(c.player.containerMenu.containerId!=0)throw new IllegalStateException("Close the container before selecting a held item");
            String item=str(r,"item");int found=-1;for(int i=0;i<36;i++)if(itemId(c.player.getInventory().getItem(i)).equals(item)){found=i;break;}
            if(found<0)throw new IllegalStateException("Missing item: "+item);
            if(found<9)c.player.getInventory().setSelectedSlot(found);
            else{int hotbar=5;c.gameMode.handleContainerInput(0,found,hotbar,ContainerInput.SWAP,c.player);c.player.getInventory().setSelectedSlot(hotbar);}
            settle(r,8);
        }else if(command.equals("distribute")){
            var menu=c.player.containerMenu;String type=menu.getClass().getSimpleName();int limit=type.equals("InventoryMenu")?4:type.equals("CraftingMenu")?9:0;
            if(limit==0 || menu.containerId!=r.get("menu_id").getAsInt())throw new IllegalStateException("Expected crafting menu changed");
            if(!itemId(menu.getCarried()).equals(str(r,"expected_cursor")) || menu.getCarried().getCount()!=r.get("expected_cursor_count").getAsInt())throw new IllegalStateException("Cursor stack changed");
            Set<Integer> slots=new LinkedHashSet<>();for(var v:r.getAsJsonArray("slots")){int i=v.getAsInt();if(i<1 || i>limit || !menu.getSlot(i).getItem().isEmpty())throw new IllegalArgumentException("Crafting grid target is occupied or invalid");slots.add(i);}
            if(slots.isEmpty() || menu.getCarried().getCount()<slots.size())throw new IllegalArgumentException("Insufficient ingredients for distribution");
            c.gameMode.handleContainerInput(menu.containerId,-999,0,ContainerInput.QUICK_CRAFT,c.player);
            for(int i:slots)c.gameMode.handleContainerInput(menu.containerId,i,1,ContainerInput.QUICK_CRAFT,c.player);
            c.gameMode.handleContainerInput(menu.containerId,-999,2,ContainerInput.QUICK_CRAFT,c.player);settle(r,8);
        }else if(command.equals("slot_click")){
            var menu=c.player.containerMenu;int slot=r.get("slot").getAsInt();
            if(menu.containerId!=r.get("menu_id").getAsInt() || slot<0 || slot>=menu.slots.size())throw new IllegalStateException("Container changed");
            if(!itemId(menu.getSlot(slot).getItem()).equals(str(r,"expected_item")))throw new IllegalStateException("Slot item changed");
            if(r.has("expected_count") && menu.getSlot(slot).getItem().getCount()!=r.get("expected_count").getAsInt())throw new IllegalStateException("Slot count changed");
            String kind=str(r,"kind");ContainerInput input=switch(kind){case "pickup"->ContainerInput.PICKUP;case "quick_move"->ContainerInput.QUICK_MOVE;case "swap"->ContainerInput.SWAP;default->throw new IllegalArgumentException("Unsupported slot action");};
            int button=r.has("button")?r.get("button").getAsInt():0;
            if(button<0 || button>(kind.equals("swap")?8:1))throw new IllegalArgumentException("Bad slot button");
            c.gameMode.handleContainerInput(menu.containerId,slot,button,input,c.player);settle(r,8);
        }else if(command.equals("interact")){
            JsonArray p=r.getAsJsonArray("pos");checkSiteTarget(r,p);BlockPos pos=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!state(c,pos).equals(str(r,"expected_state")))throw new IllegalStateException("Target block changed");
            if(!itemId(c.player.getMainHandItem()).equals(str(r,"expected_hand")))throw new IllegalStateException("Held item changed");
            Direction face=Direction.valueOf(str(r,"face").toUpperCase(Locale.ROOT));Vec3 hit=Vec3.atCenterOf(pos).add(face.getStepX()*.5,face.getStepY()*.5,face.getStepZ()*.5);
            if(c.player.getEyePosition().distanceTo(hit)>c.player.blockInteractionRange())throw new IllegalStateException("Target out of reach");
            var level=c.level;RotationAim.Look look=RotationAim.lookAt(c.player,hit);active=r.deepCopy();op="rotation";phase="running";deadline=ticks+40;
            PlacementRotation.after(c,look.yaw(),look.pitch(),()->{
                try{
                    if(active==null || !str(active,"id").equals(str(r,"id")))return;guard(c,r);if(c.level!=level || !state(c,pos).equals(str(r,"expected_state")) || !itemId(c.player.getMainHandItem()).equals(str(r,"expected_hand")))throw new IllegalStateException("Placement context changed while rotating");
                    if(c.player.getEyePosition().distanceTo(hit)>c.player.blockInteractionRange())throw new IllegalStateException("Target moved out of reach");
                    c.gameMode.useItemOn(c.player,InteractionHand.MAIN_HAND,new BlockHitResult(hit,face,pos,false));settle(r,8);
                }catch(Exception e){finish(c,"error",e.getMessage());}
            });
        }else if(command.equals("mine_block") || command.equals("recover_shulker")){
            JsonArray p=r.getAsJsonArray("pos");checkSiteTarget(r,p);BlockPos pos=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!state(c,pos).equals(str(r,"expected_state")))throw new IllegalStateException("Mining target changed");
            boolean recovery=command.equals("recover_shulker");
            boolean allowed=ContainerRecoveryPolicy.allowed(BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString(),recovery,c.player.getInventory().getFreeSlot()>=0?1:0);
            if(recovery && !allowed)throw new IllegalStateException("Shulker retrieval requires an actual shulker box and a free inventory slot");
            if(c.level.getBlockEntity(pos)!=null && !allowed)throw new IllegalStateException("Block entities and containers are protected");
            if(c.level.getBlockState(pos).getDestroySpeed(c.level,pos)<0 || c.level.isEmptyBlock(pos))throw new IllegalStateException("Target is not mineable");
            if(c.player.onGround() && c.player.blockPosition().below().equals(pos))throw new IllegalStateException("Current footing is protected");
            for(Direction d:Direction.values())if(!c.level.getFluidState(pos.relative(d)).isEmpty())throw new IllegalStateException("Fluid next to target is protected");
            if(c.player.getEyePosition().distanceTo(Vec3.atCenterOf(pos))>c.player.blockInteractionRange()-.2)throw new IllegalStateException("Mining target out of reach");
            KitClient.stopWork("切换到指定方块修正");active=r.deepCopy();op="mine_block";phase="running";detail="mining the verified target";mineStarted=false;deadline=ticks+20*Math.min(20,r.has("seconds")?r.get("seconds").getAsInt():10);
        }else if(command.equals("interact_entity")){
            var entity=c.level.getEntity(r.get("entity_id").getAsInt());
            if(entity==null || !entity.getUUID().toString().equals(str(r,"expected_uuid")))throw new IllegalStateException("Entity changed");
            Vec3 hit=entity.position().add(0,entity.getBbHeight()*.55,0);
            if(c.player.getEyePosition().distanceTo(hit)>c.player.entityInteractionRange())throw new IllegalStateException("Entity out of reach");
            RotationAim.apply(c.player,RotationAim.lookAt(c.player,hit));
            c.gameMode.interact(c.player,entity,new EntityHitResult(entity,hit),InteractionHand.MAIN_HAND);
            phase="done";detail="entity interaction sent; verify resulting world state";
        }else if(command.equals("close_menu")){
            if(!c.player.containerMenu.getCarried().isEmpty())throw new IllegalStateException("Cursor holds an item");c.player.closeContainer();phase="done";detail="menu closed";
        }else throw new IllegalArgumentException("Unknown operation");
        writeStatus(c);
    }
    private static void settle(JsonObject r,int wait){active=r.deepCopy();op="settle";phase="running";detail="awaiting server acknowledgement";deadline=ticks+wait;}
    private static void finish(Minecraft c,String p,String text){ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);active=null;phase=p;detail=text;writeStatus(c);}
    private static void restoreArrival(){if(Double.isFinite(savedArrival)){if(KitClient.config().arrivalRadius==temporaryArrival){KitClient.config().arrivalRadius=savedArrival;KitClient.config().save();}savedArrival=Double.NaN;}}
    private static void checkSiteTarget(JsonObject r,JsonArray p){JsonArray s=r.getAsJsonArray("site");if(p==null || p.size()!=3 || !Double.isFinite(p.get(1).getAsDouble()) || !AutomationScope.nearSite(p.get(0).getAsDouble()-s.get(0).getAsDouble(),p.get(2).getAsDouble()-s.get(2).getAsDouble()))throw new IllegalArgumentException("Target outside worksite");}
    private static JsonArray scan(Minecraft c,JsonObject r){
        JsonArray a=r.getAsJsonArray("min"),b=r.getAsJsonArray("max");checkSiteTarget(r,a);checkSiteTarget(r,b);
        int x1=a.get(0).getAsInt(),y1=a.get(1).getAsInt(),z1=a.get(2).getAsInt(),x2=b.get(0).getAsInt(),y2=b.get(1).getAsInt(),z2=b.get(2).getAsInt();
        if(x2<x1 || y2<y1 || z2<z1 || (long)(x2-x1+1)*(y2-y1+1)*(z2-z1+1)>50000)throw new IllegalArgumentException("Invalid scan volume");
        JsonArray rows=new JsonArray();for(int x=x1;x<=x2;x++)for(int z=z1;z<=z2;z++)for(int y=y1;y<=y2;y++){
            BlockPos p=new BlockPos(x,y,z);if(!c.level.hasChunkAt(p))throw new IllegalStateException("Chunk is not loaded: "+p);
            if(c.level.isEmptyBlock(p))continue;JsonObject v=new JsonObject();v.add("pos",JSON.toJsonTree(new int[]{x,y,z}));v.addProperty("state",state(c,p));rows.add(v);
        }return rows;
    }
    private static String state(Minecraft c,BlockPos p){return c.level.getBlockState(p).toString();}
    private static String itemId(ItemStack s){return s.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(s.getItem()).toString();}
    private static int count(Minecraft c,String id){int n=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++){ItemStack s=c.player.getInventory().getItem(i);if(itemId(s).equals(id))n+=s.getCount();}return n;}
    private static JsonObject stack(ItemStack s){
        JsonObject j=new JsonObject();j.addProperty("item",itemId(s));j.addProperty("count",s.getCount());
        var contents=s.get(net.minecraft.core.component.DataComponents.CONTAINER);
        if(contents!=null){JsonArray rows=new JsonArray();contents.nonEmptyItemCopyStream().limit(27).forEach(item->{JsonObject v=new JsonObject();v.addProperty("item",itemId(item));v.addProperty("count",item.getCount());rows.add(v);});j.add("contains",rows);}
        return j;
    }
    private static JsonObject snapshot(Minecraft c){
        JsonObject j=new JsonObject();j.addProperty("time",System.currentTimeMillis());j.addProperty("window_active",c.isWindowActive());j.addProperty("screen",c.screen==null?"":c.screen.getClass().getSimpleName());j.addProperty("connected",c.player!=null && c.level!=null);
        if(c.player==null || c.level==null)return j;
        j.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);j.addProperty("dimension",c.level.dimension().identifier().toString());
        j.add("pos",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));j.addProperty("yaw",c.player.getYRot());j.addProperty("pitch",c.player.getXRot());j.addProperty("health",c.player.getHealth());j.addProperty("food",c.player.getFoodData().getFoodLevel());
        j.addProperty("on_ground",c.player.onGround());j.addProperty("horizontal_collision",c.player.horizontalCollision);j.add("velocity",JSON.toJsonTree(new double[]{c.player.getDeltaMovement().x,c.player.getDeltaMovement().y,c.player.getDeltaMovement().z}));
        j.addProperty("selected_slot",c.player.getInventory().getSelectedSlot());JsonObject keys=new JsonObject();keys.addProperty("forward",c.options.keyUp.isDown());keys.addProperty("back",c.options.keyDown.isDown());keys.addProperty("jump",c.options.keyJump.isDown());keys.addProperty("sneak",c.options.keyShift.isDown());j.add("movement_keys",keys);
        j.add("hand",stack(c.player.getMainHandItem()));JsonArray inventory=new JsonArray();
        for(int i=0;i<c.player.getInventory().getContainerSize();i++){JsonObject s=stack(c.player.getInventory().getItem(i));s.addProperty("slot",i);inventory.add(s);}j.add("inventory",inventory);
        var menu=c.player.containerMenu;JsonObject m=new JsonObject();m.addProperty("id",menu.containerId);m.addProperty("type",menu.getClass().getSimpleName());m.add("cursor",stack(menu.getCarried()));JsonArray slots=new JsonArray();
        for(int i=0;i<menu.slots.size();i++){JsonObject s=stack(menu.getSlot(i).getItem());s.addProperty("slot",i);slots.add(s);}m.add("slots",slots);j.add("menu",m);
        j.add("build_job",KitClient.buildJob().snapshot());j.add("concrete",KitClient.concrete().snapshot());j.addProperty("guard_busy",guardBusy);j.addProperty("guard_armed",guardScope!=null);j.addProperty("guard_status",KitClient.borer().status());j.add("professional_printer",ProfessionalPrinter.status());j.addProperty("chopping",KitClient.chopper().isActive());j.addProperty("chopper_status",KitClient.chopper().status());j.addProperty("navigating",KitClient.controller().isActive());j.addProperty("printing",KitClient.machines().isPlacing());j.addProperty("printer_status",KitClient.machines().status());
        JsonArray nearby=new JsonArray();for(var e:c.level.entitiesForRendering()){
            if(e==c.player || e.distanceToSqr(c.player)>256)continue;
            JsonObject v=new JsonObject();v.addProperty("id",e.getId());v.addProperty("uuid",e.getUUID().toString());v.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());v.addProperty("name",e.getName().getString());if(e instanceof net.minecraft.world.entity.item.ItemEntity drop)v.add("stack",stack(drop.getItem()));v.add("pos",JSON.toJsonTree(new double[]{e.getX(),e.getY(),e.getZ()}));nearby.add(v);
        }j.add("entities",nearby);
        j.addProperty("kill_aura",MeteorModules.isActive(MeteorModules.KILL_AURA));j.addProperty("auto_log",MeteorModules.isActive(MeteorModules.AUTO_LOG));j.addProperty("flight",MeteorModules.isActive(MeteorModules.FLIGHT));return j;
    }
    private static void writeStatus(Minecraft c){try{JsonObject j=snapshot(c);j.addProperty("id",statusId);j.addProperty("last_request",lastId);j.addProperty("phase",phase);j.addProperty("op",op);j.addProperty("detail",detail);save(root(c).resolve("status.json"),j);}catch(Exception ignored){}}
    private static void save(Path file,JsonObject j)throws Exception{Files.createDirectories(file.getParent());Path tmp=file.resolveSibling(file.getFileName()+".tmp");Files.writeString(tmp,JSON.toJson(j));try{Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException e){Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING);}}
    private static String str(JsonObject j,String k){return j.has(k)?j.get(k).getAsString():"";}
    private static String safeId(String s){if(!s.matches("[A-Za-z0-9_-]{1,80}"))throw new IllegalArgumentException("Invalid job ID");return s;}
}
