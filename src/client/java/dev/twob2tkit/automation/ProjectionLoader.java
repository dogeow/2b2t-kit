package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Vec3i;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;

/** Public Litematica API adapter. Changes projection configuration only, never real blocks. */
final class ProjectionLoader {
    private static final Gson JSON=new GsonBuilder().setPrettyPrinting().create();
    private static final String DATA="fi.dy.masa.litematica.data.DataManager";
    private static final String PLACEMENT="fi.dy.masa.litematica.schematic.placement.SchematicPlacement";
    private static final String SCHEMATIC="fi.dy.masa.litematica.schematic.LitematicaSchematic";
    private static Undo lastUndo;
    private record Undo(String id,Object level,ProjectionLoadTransaction<Object> transaction,Access access,Object schematic,Object placement,Path journal){}
    private ProjectionLoader(){}
    static JsonObject load(Minecraft c,JsonObject raw,Runnable recheck)throws Exception{
        var request=ProjectionLoadPolicy.parse(c.gameDirectory.toPath(),raw);
        if(request.origin().getY()<c.level.getMinY()||request.origin().getY()>=c.level.getMaxY())throw new IllegalArgumentException("Projection origin Y is outside this world's build height");
        Path journal=c.gameDirectory.toPath().resolve("config/twob2tkit/automation/projection-loads").resolve(raw.get("id").getAsString()+".json");
        if(Files.exists(journal))throw new IllegalStateException("This import request already has a journal; inspect it instead of replaying the load");
        Access access=new Access();access.requireAllLayers();
        String beforeHash=hash(request.file());
        ProjectionLoadPolicy.decodedSize(request.file(),64L*1024*1024);
        Prepared prepared=access.prepare(request,c.level.getMinY(),c.level.getMaxY());
        if(!beforeHash.equals(hash(request.file())))throw new IllegalStateException("Schematic file changed while it was loading");
        recheck.run();
        String id="projection-load-"+UUID.randomUUID();
        var transaction=new ProjectionLoadTransaction<Object>(access,prepared.placement);
        var evidence=new JsonObject();evidence.addProperty("schema",1);evidence.addProperty("id",id);evidence.addProperty("world_session",raw.get("world_session").getAsString());
        evidence.addProperty("file",request.relative());evidence.addProperty("file_sha256",beforeHash);evidence.addProperty("created_at",System.currentTimeMillis());evidence.addProperty("stage","prepared");
        var previous=new JsonArray();for(var old:transaction.before())previous.add(JsonParser.parseString(old.fingerprint()));evidence.add("previous_placements",previous);
        evidence.addProperty("previous_selected_id",transaction.oldSelection()==null?"":access.identifier(transaction.oldSelection()));
        evidence.add("new_placement",access.json(prepared.placement));write(journal,evidence);
        try{
            recheck.run();transaction.apply();
            var pick=LitematicaAccess.lockedBuildSelection();
            if(access.selected()!=prepared.placement||!pick.name().equals(request.name()))throw new IllegalStateException("Imported projection selection could not be verified");
            String loading=LitematicaAccess.loadingReason(pick);
            var result=new JsonObject();result.addProperty("success",true);result.addProperty("rollback_id",id);
            result.addProperty("new_placement_id",access.identifier(prepared.placement));result.addProperty("placement_key",pick.key());
            result.add("bounds",bounds(pick.min(),pick.max()));result.add("regions",JSON.toJsonTree(prepared.regions));
            result.add("origin",JSON.toJsonTree(new int[]{request.origin().getX(),request.origin().getY(),request.origin().getZ()}));result.addProperty("rotation",request.rotation());result.addProperty("mirror",request.mirror());
            result.addProperty("file_sha256",beforeHash);result.addProperty("loading_pending",!loading.isEmpty());result.addProperty("loading_detail",loading);
            result.addProperty("selected_region_non_air_sum",prepared.nonAir);result.addProperty("old_placements_preserved",true);result.addProperty("world_blocks_changed",false);result.addProperty("entities_ignored",true);
            evidence.addProperty("stage","committed");evidence.add("result",result.deepCopy());write(journal,evidence);
            access.save(); // Litematica has a void save API; this is a request, not disk-success evidence.
            result.addProperty("litematica_save_requested",true);
            lastUndo=new Undo(id,c.level,transaction,access,prepared.schematic,prepared.placement,journal);
            return result;
        }catch(Exception failure){
            boolean restored=transaction.rollback();
            try{if(!access.all().contains(prepared.placement))access.removeOwnSchematic(prepared.schematic);else restored=false;}catch(RuntimeException cleanup){restored=false;}
            var result=new JsonObject();result.addProperty("success",false);result.addProperty("error",message(failure));result.addProperty("rollback_confirmed",restored);result.addProperty("world_blocks_changed",false);
            evidence.addProperty("stage",restored?"rolled_back":"rollback_incomplete");evidence.add("result",result.deepCopy());
            try{write(journal,evidence);}catch(Exception logFailure){result.addProperty("journal_error",message(logFailure));}
            if(restored)try{access.save();}catch(RuntimeException ignored){}
            return result;
        }
    }
    static JsonObject rollback(Minecraft c,JsonObject raw,Runnable recheck)throws Exception{
        ProjectionLoadPolicy.envelope(raw,true);
        String id=ProjectionLoadPolicy.text(raw,"rollback_id",96);var undo=lastUndo;
        if(undo==null||!undo.id.equals(id)||undo.level!=c.level)throw new IllegalStateException("No same-world rollback handle exists for this import");
        recheck.run();undo.transaction.rollbackExplicit();
        undo.access.removeOwnSchematic(undo.schematic);undo.access.save();lastUndo=null;
        var result=new JsonObject();result.addProperty("success",true);result.addProperty("rollback_id",id);result.addProperty("rollback_confirmed",true);result.addProperty("world_blocks_changed",false);
        var previous=JSON.fromJson(Files.readString(undo.journal),JsonObject.class);previous.addProperty("stage","explicitly_rolled_back");previous.addProperty("rolled_back_at",System.currentTimeMillis());write(undo.journal,previous);
        return result;
    }
    private static String message(Throwable error){while(error instanceof InvocationTargetException call&&call.getCause()!=null)error=call.getCause();return error.getMessage()==null?error.getClass().getSimpleName():error.getMessage();}
    private static String hash(Path file)throws Exception{return HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));}
    private static JsonObject bounds(BlockPos min,BlockPos max){var j=new JsonObject();j.add("min",JSON.toJsonTree(new int[]{min.getX(),min.getY(),min.getZ()}));j.add("max",JSON.toJsonTree(new int[]{max.getX(),max.getY(),max.getZ()}));return j;}
    private static void write(Path path,JsonObject data)throws Exception{Files.createDirectories(path.getParent());Path tmp=path.resolveSibling(path.getFileName()+".tmp");Files.writeString(tmp,JSON.toJson(data));try{Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException ignored){Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING);}}
    private record Prepared(Object schematic,Object placement,List<String> regions,int nonAir){}
    private static Object invoke(Object target,String name,Class<?>[] types,Object... args){
        try{return (target instanceof Class<?> type?type:target.getClass()).getMethod(name,types).invoke(target instanceof Class<?>?null:target,args);}
        catch(ReflectiveOperationException e){throw new IllegalStateException("Litematica "+name+" failed: "+message(e),e);}
    }
    private static Object call(Object target,String name){return invoke(target,name,new Class<?>[0]);}
    private static final class Access implements ProjectionLoadTransaction.Access<Object> {
        final Class<?> data,placementType,schematicType,messageType;
        final Object manager,holder,messages;
        Access()throws ReflectiveOperationException{
            data=Class.forName(DATA);placementType=Class.forName(PLACEMENT);schematicType=Class.forName(SCHEMATIC);
            messageType=Class.forName("fi.dy.masa.malilib.gui.interfaces.IMessageConsumer");
            manager=call(data,"getSchematicPlacementManager");holder=call(Class.forName("fi.dy.masa.litematica.data.SchematicHolder"),"getInstance");
            messages=Proxy.newProxyInstance(messageType.getClassLoader(),new Class<?>[]{messageType},(p,m,a)->{
                if(m.getDeclaringClass()==Object.class)return switch(m.getName()){case "toString"->"Kit projection import";case "hashCode"->System.identityHashCode(p);case "equals"->p==a[0];default->null;};return null;
            });
        }
        void requireAllLayers(){if(!((Enum<?>)call(call(data,"getRenderLayerRange"),"getLayerMode")).name().equals("ALL"))throw new IllegalStateException("Projection import requires render layer ALL; existing layer settings were not changed");}
        @SuppressWarnings("unchecked") public List<Object> all(){return new ArrayList<>((List<Object>)call(manager,"getAllSchematicsPlacements"));}
        public Object selected(){return call(manager,"getSelectedSchematicPlacement");}
        public boolean enabled(Object p){return (boolean)call(p,"isEnabled");}
        JsonObject json(Object p){return ((JsonObject)call(p,"toJson")).deepCopy();}
        public String fingerprint(Object p){return json(p).toString();}
        String identifier(Object p){return call(p,"getHashId").toString();}
        public void add(Object p){
            Object schematic=call(p,"getSchematic");invoke(holder,"addSchematic",new Class<?>[]{schematicType,boolean.class},schematic,true);
            invoke(manager,"addSchematicPlacement",new Class<?>[]{placementType,boolean.class},p,false);
        }
        public void remove(Object p){invoke(manager,"removeSchematicPlacement",new Class<?>[]{placementType,boolean.class},p,false);}
        public void enable(Object p,boolean value){invoke(p,"setEnabled",new Class<?>[]{boolean.class},value);}
        public void select(Object p){invoke(manager,"setSelectedSchematicPlacement",new Class<?>[]{placementType},p);}
        void save(){invoke(data,"save",new Class<?>[]{boolean.class},true);}
        void removeOwnSchematic(Object schematic){invoke(holder,"removeSchematic",new Class<?>[]{schematicType},schematic);}
        Prepared prepare(ProjectionLoadPolicy.Request request,int minY,int maxY)throws Exception{
            Object schematic=invoke(schematicType,"createFromFile",new Class<?>[]{Path.class,String.class},request.file().getParent(),request.file().getFileName().toString());
            if(schematic==null)throw new IllegalArgumentException("Litematica could not parse the .litematic file");
            var sizes=(Map<?,?>)call(schematic,"getAreaSizes");var positions=(Map<?,?>)call(schematic,"getAreaPositions");
            if(sizes.isEmpty()||sizes.size()>64||!sizes.keySet().equals(positions.keySet()))throw new IllegalArgumentException("Schematic requires 1..64 complete regions");
            List<String> names=request.regions().isEmpty()?sizes.keySet().stream().map(Object::toString).sorted().toList():request.regions();
            if(!sizes.keySet().containsAll(names))throw new IllegalArgumentException("Requested schematic region does not exist");
            long total=0;int nonAir=0;
            for(String name:names){
                if(!(sizes.get(name) instanceof Vec3i size)||!(positions.get(name) instanceof Vec3i pos))throw new IllegalArgumentException("Invalid region coordinates");
                total+=ProjectionLoadPolicy.volume(size.getX(),size.getY(),size.getZ());if(total>ProjectionLoadPolicy.MAX_CELLS)throw new IllegalArgumentException("Selected regions exceed 100000 cells");
                for(int v:new int[]{pos.getX(),pos.getY(),pos.getZ()})if(Math.abs((long)v)>30000000)throw new IllegalArgumentException("Region position exceeds world coordinates");
                Object container=invoke(schematic,"getSubRegionContainer",new Class<?>[]{String.class},name);
                if(container==null)throw new IllegalArgumentException("Schematic region has no block-state container");
                Vec3i actual=(Vec3i)call(container,"getSize");
                if(actual.getX()!=Math.abs((long)size.getX())||actual.getY()!=Math.abs((long)size.getY())||actual.getZ()!=Math.abs((long)size.getZ()))throw new IllegalArgumentException("Region block-state dimensions do not match its size");
                Method get=container.getClass().getMethod("get",int.class,int.class,int.class);
                for(int x=0;x<actual.getX();x++)for(int y=0;y<actual.getY();y++)for(int z=0;z<actual.getZ();z++){
                    BlockState state=(BlockState)get.invoke(container,x,y,z);if(!state.isAir()&&!state.is(Blocks.STRUCTURE_VOID))nonAir++;
                }
            }
            if(nonAir==0)throw new IllegalArgumentException("Selected schematic regions contain no buildable blocks");
            Object placement=invoke(placementType,"createFor",new Class<?>[]{schematicType,BlockPos.class,String.class,boolean.class,boolean.class},schematic,request.origin(),request.name(),false,true);
            invoke(placement,"setRotation",new Class<?>[]{Rotation.class,messageType},Rotation.valueOf(request.rotation()),messages);
            invoke(placement,"setMirror",new Class<?>[]{Mirror.class,messageType},Mirror.valueOf(request.mirror()),messages);
            var regions=(Collection<?>)call(placement,"getAllSubRegionsPlacements");
            var excluded=regions.stream().filter(p->!names.contains(call(p,"getName").toString())).toList();
            if(!excluded.isEmpty())invoke(placement,"setSubRegionsEnabledState",new Class<?>[]{boolean.class,Collection.class,messageType},false,excluded,messages);
            for(Object region:regions)if(names.contains(call(region,"getName").toString()))invoke(region,"setRenderingEnabled",new Class<?>[]{boolean.class},true);
            if(!(boolean)call(placement,"ignoreEntities"))invoke(placement,"toggleIgnoreEntities",new Class<?>[]{messageType},messages);
            if(!(boolean)call(placement,"isLocked"))call(placement,"toggleLocked");
            Class<?> requirement=Class.forName("fi.dy.masa.litematica.schematic.placement.SubRegionPlacement$RequiredEnabled");
            var boxes=(Map<?,?>)invoke(placement,"getSubRegionBoxes",new Class<?>[]{requirement},requirement.getField("ANY").get(null));
            int lx=Integer.MAX_VALUE,ly=Integer.MAX_VALUE,lz=Integer.MAX_VALUE,hx=Integer.MIN_VALUE,hy=Integer.MIN_VALUE,hz=Integer.MIN_VALUE;
            for(String name:names){Object box=boxes.get(name);if(box==null)throw new IllegalArgumentException("Region has no transformed placement bounds");BlockPos a=(BlockPos)call(box,"getPos1"),b=(BlockPos)call(box,"getPos2");
                lx=Math.min(lx,Math.min(a.getX(),b.getX()));ly=Math.min(ly,Math.min(a.getY(),b.getY()));lz=Math.min(lz,Math.min(a.getZ(),b.getZ()));hx=Math.max(hx,Math.max(a.getX(),b.getX()));hy=Math.max(hy,Math.max(a.getY(),b.getY()));hz=Math.max(hz,Math.max(a.getZ(),b.getZ()));}
            if(ly<minY||hy>=maxY||lx<-29999984||hx>29999984||lz<-29999984||hz>29999984)throw new IllegalArgumentException("Transformed schematic exceeds this world's build bounds");
            ProjectionLoadPolicy.volume(hx-lx+1,hy-ly+1,hz-lz+1);
            return new Prepared(schematic,placement,List.copyOf(names),nonAir);
        }
    }
}
