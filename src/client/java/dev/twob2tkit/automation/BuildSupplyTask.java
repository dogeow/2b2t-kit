package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.*;
import dev.twob2tkit.builder.BuildSupplyPlan;
import dev.twob2tkit.runtime.api.BuildNavigation;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.*;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.*;
import java.util.*;

/** A single verified depot visit. Cruise and PvE remain owned by existing Kit systems. */
public final class BuildSupplyTask {
    private static final Gson JSON=new Gson();
    private static String historyJob="";
    private static final Map<String,Integer> visits=new HashMap<>();
    private final ClientLevel level;
    private final String job,sourceKey,blockId;
    private final boolean approachOnly;
    private final String expectedState;
    private final Direction interactionFace;
    private final double standDistance;
    private final net.minecraft.world.entity.item.ItemEntity drop;
    private final String dropItem;
    private final int dropBefore,dropCount;
    private int missingDropTicks;
    private final BlockPos source;
    private final Map<String,Integer> targets,taken=new TreeMap<>();
    private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private Vec3 destination;
    private BlockPos start;
    private final BuildNavigation navigation;
    private BuildNavigation.Search search;
    private Vec3 searchOrigin;
    private BlockPos boundMin,boundMax;
    private int searchExpanded;
    private List<BlockPos> path=List.of();
    private int pathIndex,stall;
    private double bestDistance=Double.POSITIVE_INFINITY;
    private String phase="travel",failure="";
    private int tick,menuId=-1,openTick,settleTick,clicks,pendingSlot=-1,beforeCount,sourceBefore,expectedCount;
    private String pendingItem="";
    private boolean closed,arrived;
    private RotationAim.Look travelLook;
    public record Source(String key,KitConfig.StorageSnapshot record,double distance){}

    public static Map<String,Integer> inventory(Minecraft c){
        var result=new HashMap<String,Integer>();
        for(int i=0;i<36;i++){var stack=c.player.getInventory().getItem(i);if(!stack.isEmpty())result.merge(id(stack),stack.getCount(),Integer::sum);}return result;
    }
    private static String id(ItemStack s){return s.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(s.getItem()).toString();}
    private static Map<String,Integer> needed(){var r=new TreeMap<String,Integer>();KitClient.buildJob().snapshot().getAsJsonObject("material_needs").entrySet().forEach(e->r.put(e.getKey(),e.getValue().getAsInt()));return r;}
    public static int room(Minecraft c,String item){
        int room=0;
        for(int i=0;i<36;i++){var stack=c.player.getInventory().getItem(i);if(stack.isEmpty())return 64;if(id(stack).equals(item))room+=Math.max(0,stack.getMaxStackSize()-stack.getCount());}return room;
    }
    private static String server(Minecraft c){return c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;}
    private static String worldId(Minecraft c){return c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString();}
    public static boolean sourceEnabled(Minecraft c,KitConfig.StorageSnapshot record){
        var sources=KitClient.config().projectionSupplySources;
        return sources!=null && sources.stream().anyMatch(s->AutomationScope.sameServer(server(c),s.server)&&worldId(c).equals(s.worldId)&&s.dimension.equals(record.dimension)&&s.x==record.x&&s.y==record.y&&s.z==record.z);
    }
    public static void toggleSource(Minecraft c,KitConfig.StorageSnapshot record){
        if(c.player==null||c.level==null||!record.dimension.equals(c.level.dimension().identifier().toString()))throw new IllegalStateException("请先进入这个仓库所在的世界");
        var config=KitClient.config();if(config.projectionSupplySources==null)config.projectionSupplySources=new ArrayList<>();
        boolean exists=sourceEnabled(c,record);
        config.projectionSupplySources.removeIf(s->AutomationScope.sameServer(server(c),s.server)&&worldId(c).equals(s.worldId)&&s.dimension.equals(record.dimension)&&s.x==record.x&&s.y==record.y&&s.z==record.z);
        if(!exists){var s=new KitConfig.ProjectionSupplySource();s.server=server(c);s.worldId=worldId(c);s.dimension=record.dimension;s.x=record.x;s.y=record.y;s.z=record.z;config.projectionSupplySources.add(s);}config.save();
    }
    public static List<Source> sources(Minecraft c){
        var list=new ArrayList<Source>();
        try{
            var b=KitClient.buildJob().snapshot();String session=b.get("session").getAsString();
            if(!session.equals(historyJob)){historyJob=session;visits.clear();}
            if(b.get("active").getAsBoolean() || !Set.of("missing_materials","blocked").contains(b.get("outcome").getAsString()) || !KitClient.buildJob().supervisionScopeCurrent(c))return list;
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip,dim=c.level.dimension().identifier().toString();
            var wanted=BuildSupplyPlan.targets(needed(),inventory(c));
            var config=KitClient.config();
            if(config.projectionSupplySources==null)return list;
            for(var allowed:config.projectionSupplySources){
                if(!AutomationScope.sameServer(server,allowed.server) || !dim.equals(allowed.dimension))continue;
                // A singleplayer permission must also identify its exact save folder.
                if(server.equals("singleplayer") && !c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString().equals(allowed.worldId))continue;
                String key=allowed.dimension+":"+allowed.x+":"+allowed.y+":"+allowed.z;
                if(visits.getOrDefault(key,0)>=1)continue;
                var pos=new BlockPos(allowed.x,allowed.y,allowed.z);double distance=c.player.position().distanceTo(Vec3.atCenterOf(pos));
                if(distance>128 || !c.level.hasChunkAt(pos))continue;
                var record=config.storageSnapshots.stream().filter(r->r.key().equals(key)).findFirst().orElse(null);
                if(record==null || record.items==null || record.items.stream().noneMatch(i->i.count>0 && wanted.containsKey(i.id) && room(c,i.id)>0))continue;
                String actual=BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString();
                if(!actual.equals(record.blockId) || !(actual.equals("minecraft:chest") || actual.equals("minecraft:trapped_chest") || actual.equals("minecraft:barrel") || actual.endsWith("shulker_box")))continue;
                list.add(new Source(key,record,distance));
            }
            list.sort(Comparator.comparingDouble(Source::distance));
        }catch(Exception ignored){}return list;
    }
    public static JsonArray candidates(Minecraft c){
        var out=new JsonArray();var wanted=c.player==null?Map.<String,Integer>of():BuildSupplyPlan.targets(needed(),inventory(c));
        for(var s:sources(c).stream().limit(3).toList()){
            var j=new JsonObject();j.addProperty("key",s.key);j.addProperty("distance",Math.round(s.distance));j.addProperty("recorded_at",s.record.lastSeenEpochMillis);
            j.add("pos",JSON.toJsonTree(new int[]{s.record.x,s.record.y,s.record.z}));var items=new JsonObject();
            s.record.items.stream().filter(i->wanted.containsKey(i.id)).forEach(i->items.addProperty(i.id,i.count));j.add("recorded_items",items);out.add(j);
        }return out;
    }
    public BuildSupplyTask(Minecraft c,String expectedJob,String key)throws Exception{this(c,expectedJob,key,null);}
    public static BuildSupplyTask collect(Minecraft c,JsonObject request)throws Exception{
        var targets=new TreeMap<String,Integer>();
        for(var e:request.getAsJsonObject("materials").entrySet()){
            int count=e.getValue().getAsInt();if(!e.getKey().matches("minecraft:[a-z0-9_]+")||count<1||count>4096)throw new IllegalArgumentException("Invalid material target");targets.put(e.getKey(),count);
        }
        if(targets.isEmpty()||targets.size()>16)throw new IllegalArgumentException("Supply list must contain 1..16 items");
        return new BuildSupplyTask(c,null,request.get("source_key").getAsString(),targets);
    }
    public static BuildSupplyTask approach(Minecraft c,JsonObject request)throws Exception{
        var coordinates=request.getAsJsonArray("pos");
        if(coordinates==null||coordinates.size()!=3)throw new IllegalArgumentException("Target position required");
        for(var value:coordinates){double number=value.getAsDouble();if(!Double.isFinite(number)||number!=Math.rint(number))throw new IllegalArgumentException("Integer work block coordinates required");}
        var pos=new BlockPos(coordinates.get(0).getAsInt(),coordinates.get(1).getAsInt(),coordinates.get(2).getAsInt());
        Direction face=Direction.valueOf(request.get("face").getAsString().toUpperCase(Locale.ROOT));
        return new BuildSupplyTask(c,null,"approach:"+pos.toShortString(),Map.of(),pos,request.get("expected_state").getAsString(),face,request.has("stand_distance")?request.get("stand_distance").getAsDouble():-1,null);
    }
    public static BuildSupplyTask pickup(Minecraft c,JsonObject request)throws Exception{
        java.util.UUID uuid=java.util.UUID.fromString(request.get("expected_uuid").getAsString());
        for(var entity:c.level.entitiesForRendering())if(entity instanceof net.minecraft.world.entity.item.ItemEntity drop&&drop.getUUID().equals(uuid)){
            if(!drop.isAlive()||drop.distanceTo(c.player)>32||!id(drop.getItem()).equals(request.get("expected_item").getAsString())||drop.getItem().getCount()!=request.get("expected_count").getAsInt())throw new IllegalStateException("Drop identity or stack changed");
            int capacity=0;for(int n=0;n<36;n++){var held=c.player.getInventory().getItem(n);if(held.isEmpty())capacity+=drop.getItem().getMaxStackSize();else if(ItemStack.isSameItemSameComponents(held,drop.getItem()))capacity+=held.getMaxStackSize()-held.getCount();}
            if(capacity<drop.getItem().getCount())throw new IllegalStateException("Insufficient room for the observed drop");
            return new BuildSupplyTask(c,null,"drop:"+uuid,Map.of(),drop.blockPosition(),"",Direction.UP,-1,drop);
        }
        throw new IllegalStateException("Drop is no longer loaded; observe again");
    }
    static boolean pickupIntersects(AABB playerBody,AABB itemBody){return playerBody.inflate(1,.5,1).deflate(.15).intersects(itemBody);}
    private static Source approvedSource(Minecraft c,String key){
        var record=KitClient.config().storageSnapshots.stream().filter(r->r.key().equals(key)).findFirst().orElseThrow(()->new IllegalStateException("Depot has no record"));
        if(!sourceEnabled(c,record)||!record.dimension.equals(c.level.dimension().identifier().toString()))throw new IllegalStateException("Depot is not approved in this world");
        var pos=new BlockPos(record.x,record.y,record.z);double distance=c.player.position().distanceTo(Vec3.atCenterOf(pos));
        String actual=BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString();
        if(distance>128||!c.level.hasChunkAt(pos)||!actual.equals(record.blockId)||!(actual.equals("minecraft:chest")||actual.equals("minecraft:barrel")||actual.equals("minecraft:trapped_chest")||actual.endsWith("shulker_box")))throw new IllegalStateException("Depot block or distance changed");
        return new Source(key,record,distance);
    }
    private BuildSupplyTask(Minecraft c,String expectedJob,String key,Map<String,Integer> materialTargets)throws Exception{
        this(c,expectedJob,key,materialTargets,null,null,Direction.UP,-1,null);
    }
    private BuildSupplyTask(Minecraft c,String expectedJob,String key,Map<String,Integer> materialTargets,BlockPos approach,String expected,Direction face,double standDistance,net.minecraft.world.entity.item.ItemEntity drop)throws Exception{
        var b=KitClient.buildJob().snapshot();
        if(expectedJob!=null&&!b.get("session").getAsString().equals(expectedJob) || c.screen!=null || c.player.getHealth()<14 || !c.player.containerMenu.getCarried().isEmpty())throw new IllegalStateException("Supply start context changed");
        this.drop=drop;dropItem=drop==null?"":id(drop.getItem());dropBefore=drop==null?0:inventory(c).getOrDefault(dropItem,0);dropCount=drop==null?0:drop.getItem().getCount();
        approachOnly=approach!=null;expectedState=expected;interactionFace=face;
        if(!Double.isFinite(standDistance)||standDistance!=-1&&(standDistance<.25||standDistance>3))throw new IllegalArgumentException("Invalid standing distance");this.standDistance=standDistance;
        navigation=KitClient.borer().buildNavigation();level=c.level;job=expectedJob;sourceKey=key;
        if(drop!=null){source=drop.blockPosition().immutable();blockId="";}else if(approachOnly){
            if(!c.level.hasChunkAt(approach)||c.player.position().distanceTo(Vec3.atCenterOf(approach))>128)throw new IllegalStateException("Work block is unloaded or too far away");
            var state=c.level.getBlockState(approach);
            if(!state.toString().equals(expected)||state.isAir()||!state.getFluidState().isEmpty())throw new IllegalStateException("Work block state changed");
            source=approach.immutable();blockId=BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
        }else{
            var chosen=materialTargets==null?sources(c).stream().filter(s->s.key.equals(key)).findFirst().orElseThrow(()->new IllegalStateException("Depot is no longer an authorized candidate")):approvedSource(c,key);
            source=new BlockPos(chosen.record.x,chosen.record.y,chosen.record.z);blockId=chosen.record.blockId;
        }
        targets=materialTargets==null?BuildSupplyPlan.targets(needed(),inventory(c)):Map.copyOf(materialTargets);start=c.player.blockPosition();
        boundMin=new BlockPos(Math.min(source.getX(),start.getX())-8,Math.min(source.getY(),start.getY())-4,Math.min(source.getZ(),start.getZ())-8);
        boundMax=new BlockPos(Math.max(source.getX(),start.getX())+8,Math.max(source.getY(),start.getY())+8,Math.max(source.getZ(),start.getZ())+8);
        try{
            var selected=LitematicaAccess.buildSelection();
            if(selected.volume()<=300000&&(selected.contains(start)||selected.contains(source))){
                boundMin=new BlockPos(Math.min(boundMin.getX(),selected.min().getX()-5),Math.min(boundMin.getY(),selected.min().getY()-2),Math.min(boundMin.getZ(),selected.min().getZ()-5));
                boundMax=new BlockPos(Math.max(boundMax.getX(),selected.max().getX()+5),Math.max(boundMax.getY(),selected.max().getY()+5),Math.max(boundMax.getZ(),selected.max().getZ()+5));
            }
        }catch(Exception ignored){ /* Supply also works without a projection. */ }

        var goals=approaches(c);if(goals.isEmpty())throw new IllegalStateException("No visible collision-free depot approach");
        BlockPos routeStart=null;double nearest=Double.POSITIVE_INFINITY;
        for(var p:BlockPos.betweenClosed(start.offset(-1,-1,-1),start.offset(1,1,1))){
            var q=p.immutable();var delta=feet(q).subtract(c.player.position());
            if(clear(c,q) && c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(delta)) && delta.lengthSqr()<nearest){routeStart=q;nearest=delta.lengthSqr();}
        }
        if(routeStart==null)throw new IllegalStateException("No collision-free start for depot path");
        search=navigation.search(new BuildNavigation.World(){public boolean clear(BlockPos p){return BuildSupplyTask.this.clear(c,p);}public boolean edge(BlockPos a,BlockPos b){return c.level.noCollision(c.player,body(feet(a)).expandTowards(feet(b).subtract(feet(a))));}},routeStart,goals);
        searchOrigin=c.player.position();phase="planning";visits.put(key,1);
        flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/build-supply-flight-speed.bak"));
        String error=flight.acquire(c.player);if(error!=null)throw new IllegalStateException(error);flight.hover();
    }
    private static Vec3 feet(BlockPos p){return new Vec3(p.getX()+.5,p.getY()+.02,p.getZ()+.5);}
    private static AABB body(Vec3 feet){return new AABB(feet.x-.31,feet.y+.01,feet.z-.31,feet.x+.31,feet.y+1.82,feet.z+.31);}
    private boolean clear(Minecraft c,BlockPos p){
        if(p.getX()<boundMin.getX()||p.getX()>boundMax.getX()||p.getY()<boundMin.getY()||p.getY()>boundMax.getY()||p.getZ()<boundMin.getZ()||p.getZ()>boundMax.getZ())return false;
        if(!c.level.hasChunkAt(p) || !c.level.noCollision(c.player,body(feet(p))))return false;
        for(int dy=0;dy<2;dy++){var state=c.level.getBlockState(p.above(dy));if(!state.getFluidState().isEmpty() || state.is(net.minecraft.world.level.block.Blocks.FIRE) || state.is(net.minecraft.world.level.block.Blocks.SOUL_FIRE) || state.is(net.minecraft.world.level.block.Blocks.COBWEB) || state.is(net.minecraft.world.level.block.Blocks.POWDER_SNOW))return false;}return true;
    }
    static Iterable<BlockPos> approachCandidates(BlockPos source){return BlockPos.betweenClosed(source.offset(-2,-3,-2),source.offset(2,2,2));}
    private Set<BlockPos> approaches(Minecraft c){
        var goals=new HashSet<BlockPos>();
        for(var p:approachCandidates(source)){
            if(drop!=null){
                var futureBody=c.player.getBoundingBox().move(feet(p).subtract(c.player.position()));
                if(clear(c,p)&&pickupIntersects(futureBody,drop.getBoundingBox()))goals.add(p.immutable());
                continue;
            }
            if(!clear(c,p))continue;
            Vec3 eye=feet(p).add(0,c.player.getEyeHeight(),0);
            var ray=BlockFaceTarget.visible(c,eye,source,approachOnly?interactionFace:null,c.player.blockInteractionRange()-.6);
            if(ray!=null&&(!approachOnly||standDistance<=0||feet(p).distanceTo(ray.getLocation())<=standDistance))goals.add(p.immutable());
        }return goals;
    }
    private boolean move(Minecraft c){
        release(c);travelLook=null;
        if(pathIndex>=path.size()){flight.hover();return true;}
        var q=path.get(pathIndex);var delta=feet(q).subtract(c.player.position());double distance=delta.length();
        var motion=navigation.motion(delta);
        if(motion.arrived()){pathIndex++;stall=0;bestDistance=Double.POSITIVE_INFINITY;flight.hover();return false;}
        if(!clear(c,q))throw new IllegalStateException("Depot route changed; movement stopped");
        if(distance<bestDistance-.015){bestDistance=distance;stall=0;}else if(++stall>60)throw new IllegalStateException("Depot route has no verified movement");
        boolean vertical=motion.vertical();var probe=motion.probe();
        if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(probe)))throw new IllegalStateException("Actual collision on depot route");
        if(vertical){flight.speed(motion.speed());c.options.keyJump.setDown(delta.y>0);c.options.keyShift.setDown(delta.y<0);}
        else{travelLook=new RotationAim.Look(RotationAim.yawToward(delta.x,delta.z),0);RotationAim.apply(c.player,travelLook);flight.speed(motion.speed());c.options.keyUp.setDown(true);}
        return false;
    }
    private static void release(Minecraft c){if(c.options==null)return;c.options.keyUp.setDown(false);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);}
    public void input(Minecraft c){
        if(!phase.equals("travel") || c.player==null || c.level!=level || c.screen!=null)return;
        if(drop!=null&&!drop.isAlive()){release(c);flight.hover();return;}
        try{arrived=move(c);}catch(Exception e){fail(c,e.getMessage());}
    }
    public void reapply(Minecraft c){if(!closed && phase.equals("travel") && travelLook!=null && c.player!=null && c.screen==null)RotationAim.apply(c.player,travelLook);}
    public boolean ownsMenu(Minecraft c){return phase.equals("opening") && c.player!=null && (c.player.containerMenu instanceof ChestMenu || c.player.containerMenu instanceof ShulkerBoxMenu) || menuId>=0 && c.player!=null && c.player.containerMenu.containerId==menuId;}
    public boolean done(){return phase.equals("done");}
    public String failure(){return failure;}
    public JsonObject snapshot(){var j=new JsonObject();j.addProperty("phase",phase);j.addProperty("navigation_version",navigation.version());j.addProperty("search_expanded",searchExpanded);j.addProperty("source",sourceKey);j.addProperty("approach_only",approachOnly);j.addProperty("collecting_drop",drop!=null);j.addProperty("failure",failure);j.add("taken",JSON.toJsonTree(taken));j.addProperty("clicks",clicks);j.addProperty("path_step",pathIndex);j.addProperty("path_length",path.size());if(pathIndex<path.size())j.addProperty("next_waypoint",path.get(pathIndex).toShortString());return j;}
    public void tick(Minecraft c)throws Exception{
        // input() may already have detected a collision. Preserve that terminal reason.
        if(closed||done()||!failure.isEmpty())return;
        tick++;
        if(c.level!=level || job!=null&&(!KitClient.buildJob().supervisionScopeCurrent(c) || !KitClient.buildJob().snapshot().get("session").getAsString().equals(job)))throw new IllegalStateException("Supply world/job/placement changed");
        if(AutomationBridge.guardBusy() || c.player.getHealth()<14)return;
        if(phase.equals("planning")){
            if(c.player.position().distanceToSqr(searchOrigin)>.75*.75)throw new IllegalStateException("Depot search start moved; inspect the new position");
            var p=navigation.policy();var result=search.advance(Math.min(p.sliceNodes(),p.totalNodes()-search.expanded()),System.nanoTime()+p.sliceNanos());searchExpanded=search.expanded();
            if(result==null){if(searchExpanded>=p.totalNodes())throw new IllegalStateException("Depot search budget reached; route existence is still unknown");return;}
            search=null;
            if(result.nodes().isEmpty())throw new IllegalStateException("No loaded collision-free route to this depot; no ceiling is broken");
            path=result.nodes();destination=feet(path.getLast());phase="travel";return;
        }
        if(drop!=null){
            int gained=inventory(c).getOrDefault(dropItem,0)-dropBefore;
            if(gained>=dropCount&&(!drop.isAlive()||c.level.getEntity(drop.getId())!=drop||drop.getItem().isEmpty())){taken.put(dropItem,gained);phase="done";close(c);return;}
            if(!drop.isAlive()){if(++missingDropTicks>40)throw new IllegalStateException("Drop disappeared without inventory confirmation");return;}
            if(c.screen!=null)throw new IllegalStateException("Menu interrupted drop collection");
            if(arrived){if(openTick==0)openTick=tick;if(tick-openTick>40)throw new IllegalStateException("Drop pickup not confirmed at the reached position");}
            return;
        }
        if(approachOnly&&!c.level.getBlockState(source).toString().equals(expectedState))throw new IllegalStateException("Work block state changed during approach");
        if(!BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(source).getBlock()).toString().equals(blockId))throw new IllegalStateException("Depot block changed");
        if(AutomationBridge.guardBusy() || c.player.getHealth()<14)return;
        if(phase.equals("travel")){
            if(c.screen!=null)throw new IllegalStateException("Manual menu interrupted depot travel");
            if(!arrived)return;
            if(c.player.position().distanceTo(destination)>1.6)throw new IllegalStateException("Cruise ended outside depot reach");
            var ray=BlockFaceTarget.visible(c,c.player.getEyePosition(),source,approachOnly?interactionFace:null,c.player.blockInteractionRange()-.1);
            if(ray==null)throw new IllegalStateException("Depot approach occluded or out of reach");
            if(approachOnly){if(standDistance>0&&c.player.position().distanceTo(ray.getLocation())>standDistance+.15)throw new IllegalStateException("Standing target not reached");phase="done";close(c);return;}
            RotationAim.apply(c.player,RotationAim.lookAt(c.player,ray.getLocation()));KitClient.noteStorageClick(source);
            c.gameMode.useItemOn(c.player,InteractionHand.MAIN_HAND,ray);phase="opening";openTick=tick;return;
        }
        var menu=c.player.containerMenu;
        if(phase.equals("opening")){
            if(menu.containerId==0){if(tick-openTick>60)throw new IllegalStateException("Depot opening not acknowledged");return;}
            if(!(menu instanceof ChestMenu || menu instanceof ShulkerBoxMenu))throw new IllegalStateException("Unexpected depot menu");
            menuId=menu.containerId;phase="withdraw";settleTick=tick+10;return;
        }
        if(menu.containerId!=menuId || !menu.getCarried().isEmpty())throw new IllegalStateException("Depot menu or carried stack changed");
        if(tick<settleTick)return;
        var stock=inventory(c);
        if(pendingSlot>=0){
            var stack=menu.getSlot(pendingSlot).getItem();int afterSource=id(stack).equals(pendingItem)?stack.getCount():stack.isEmpty()?0:-1;
            if(BuildSupplyPlan.confirmed(beforeCount,stock.getOrDefault(pendingItem,0),sourceBefore,afterSource,expectedCount)){
                taken.merge(pendingItem,expectedCount,Integer::sum);pendingSlot=-1;
            }else if(tick-settleTick>60)throw new IllegalStateException("Withdrawal not confirmed; no repeat click");
            else return;
        }
        if(clicks<8)for(int i=0;i<menu.slots.size();i++){
            var slot=menu.getSlot(i);if(slot.container==c.player.getInventory() || !slot.hasItem())continue;
            var stack=slot.getItem();String item=id(stack);if(stock.getOrDefault(item,0)>=targets.getOrDefault(item,0))continue;
            int capacity=0;for(int n=0;n<36;n++){var carried=c.player.getInventory().getItem(n);if(carried.isEmpty())capacity+=stack.getMaxStackSize();else if(ItemStack.isSameItemSameComponents(carried,stack))capacity+=Math.max(0,stack.getMaxStackSize()-carried.getCount());}
            int transfer=Math.min(capacity,stack.getCount());if(transfer<=0)continue;
            pendingSlot=i;pendingItem=item;beforeCount=stock.getOrDefault(item,0);sourceBefore=stack.getCount();expectedCount=transfer;
            c.gameMode.handleContainerInput(menuId,i,0,ContainerInput.QUICK_MOVE,c.player);clicks++;settleTick=tick+8;return;
        }
        c.player.closeContainer();phase="done";close(c);
    }
    public void fail(Minecraft c,String why){if(!failure.isEmpty())return;failure=why;phase="failed";close(c);}
    public void close(Minecraft c){
        if(closed)return;closed=true;
        release(c);travelLook=null;flight.hover();
        if(c.player!=null && menuId>=0 && c.player.containerMenu.containerId==menuId && c.player.containerMenu.getCarried().isEmpty())c.player.closeContainer();
        if(c.player!=null && !c.player.onGround())flight.closeKeepingFlight();else flight.close();
    }
}
