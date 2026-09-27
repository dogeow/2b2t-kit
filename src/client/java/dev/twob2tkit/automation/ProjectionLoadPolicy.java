package dev.twob2tkit.automation;

import com.google.gson.*;
import net.minecraft.core.BlockPos;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/** Strict local import request; no server commands, world writes or arbitrary filesystem paths. */
final class ProjectionLoadPolicy {
    static final int SCHEMA=1, MAX_CELLS=100000;
    static final long MAX_FILE_BYTES=16L*1024*1024;
    private static final Set<String> COMMON=Set.of("schema","id","op","server","dimension","site","world_session","expected_revision","expires_at","manual_start");
    record Request(Path file,String relative,String name,BlockPos origin,String rotation,String mirror,List<String> regions){}
    private ProjectionLoadPolicy(){}
    static void envelope(JsonObject request,boolean rollback){
        if(!text(request,"id",96).matches("[A-Za-z0-9_-]{1,96}"))throw new IllegalArgumentException("Invalid projection import request id");
        if(!text(request,"op",40).equals(rollback?"projection_load_rollback":"projection_load"))throw new IllegalArgumentException("Projection import operation does not match schema");
        var allowed=new HashSet<>(COMMON);allowed.addAll(rollback?Set.of("rollback_id"):Set.of("file","name","origin","rotation","mirror","regions"));
        for(String key:request.keySet())if(!allowed.contains(key))throw new IllegalArgumentException("Unsupported projection-load field: "+key);
        if(integer(request,"schema")!=SCHEMA)throw new IllegalArgumentException("projection_load requires schema=1");
        var manual=request.get("manual_start");if(manual==null||!manual.isJsonPrimitive()||!manual.getAsJsonPrimitive().isBoolean()||!manual.getAsBoolean())throw new IllegalArgumentException("projection_load requires manual_start=true");
        if(rollback&&!text(request,"rollback_id",96).matches("[A-Za-z0-9_-]{1,96}"))throw new IllegalArgumentException("Invalid rollback_id");
    }
    static Request parse(Path game,JsonObject request)throws IOException{
        envelope(request,false);
        String file=text(request,"file",1024),name=text(request,"name",128),rotation=text(request,"rotation",32),mirror=text(request,"mirror",32);
        if(name.isBlank()||name.chars().anyMatch(Character::isISOControl))throw new IllegalArgumentException("Projection name is empty or invalid");
        if(!Set.of("NONE","CLOCKWISE_90","CLOCKWISE_180","COUNTERCLOCKWISE_90").contains(rotation))throw new IllegalArgumentException("Unsupported projection rotation");
        if(!Set.of("NONE","LEFT_RIGHT","FRONT_BACK").contains(mirror))throw new IllegalArgumentException("Unsupported projection mirror");
        var point=request.getAsJsonArray("origin");if(point==null||point.size()!=3)throw new IllegalArgumentException("Projection origin requires integer [x,y,z]");
        int[] xyz=new int[3];for(int i=0;i<3;i++){long n=integer(point.get(i));if(n<Integer.MIN_VALUE||n>Integer.MAX_VALUE)throw new IllegalArgumentException("Projection origin exceeds integer coordinates");xyz[i]=(int)n;}
        if(Math.abs((long)xyz[0])>29999000||Math.abs((long)xyz[2])>29999000)throw new IllegalArgumentException("Projection origin exceeds world border");
        var regions=new ArrayList<String>();
        if(request.has("regions")){
            var names=request.getAsJsonArray("regions");if(names==null||names.isEmpty()||names.size()>64)throw new IllegalArgumentException("regions must contain 1..64 names");
            for(var value:names){if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isString())throw new IllegalArgumentException("Region names must be strings");String region=value.getAsString();if(region.isBlank()||region.length()>128||region.chars().anyMatch(Character::isISOControl)||regions.contains(region))throw new IllegalArgumentException("Invalid or duplicate region name");regions.add(region);}
        }
        return new Request(resolve(game,file),file,name,new BlockPos(xyz[0],xyz[1],xyz[2]),rotation,mirror,List.copyOf(regions));
    }
    static Path resolve(Path game,String filename)throws IOException{
        if(filename==null||filename.isBlank()||filename.length()>1024||filename.chars().anyMatch(Character::isISOControl)||!filename.endsWith(".litematic"))throw new IllegalArgumentException("Expected a relative .litematic file inside schematics");
        Path relative=Path.of(filename);if(relative.isAbsolute())throw new IllegalArgumentException("Absolute schematic paths are not allowed");
        for(var part:relative)if(part.toString().equals(".."))throw new IllegalArgumentException("Schematic path cannot traverse parents");
        Path root=game.toAbsolutePath().resolve("schematics").normalize().toRealPath();
        Path file=root.resolve(relative).normalize().toRealPath();
        if(!file.startsWith(root)||!Files.isRegularFile(file))throw new IllegalArgumentException("Schematic symlink/path escapes schematics");
        long size=Files.size(file);if(size<1||size>MAX_FILE_BYTES)throw new IllegalArgumentException("Schematic file must be 1 byte..16 MiB");return file;
    }
    static long decodedSize(Path file,long limit)throws IOException{
        try(var input=new java.util.zip.GZIPInputStream(Files.newInputStream(file))){
            int first=input.read();if(first!=10)throw new IllegalArgumentException("Litematic root must be a compressed NBT compound");
            long total=1;byte[] buffer=new byte[8192];int count;
            while((count=input.read(buffer))!=-1){total+=count;if(total>limit)throw new IllegalArgumentException("Expanded litematic data exceeds the bounded import size");}
            return total;
        }
    }
    static void scope(boolean alive,boolean idle,boolean healthy,boolean manual,boolean safeScreen,boolean unlocked,
                      String requestedWorld,String world,long requestedRevision,long revision,long expires,long now){
        if(!alive||!idle||!healthy||manual||!safeScreen||!unlocked||requestedWorld==null||requestedWorld.isBlank()
                ||!requestedWorld.equals(world)||requestedRevision!=revision||expires<now||expires-now>15000)
            throw new IllegalStateException("Projection import needs an idle, healthy, current world/controller and unexpired explicit request");
    }
    static long volume(int x,int y,int z){
        long a=Math.abs((long)x),b=Math.abs((long)y),c=Math.abs((long)z);
        if(a==0||b==0||c==0||a>MAX_CELLS||b>MAX_CELLS||c>MAX_CELLS||a*b>MAX_CELLS||a*b*c>MAX_CELLS)throw new IllegalArgumentException("Projection region exceeds bounded volume or has zero size");return a*b*c;
    }
    static String text(JsonObject request,String key,int limit){var value=request.get(key);if(value==null||!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isString()||value.getAsString().length()>limit)throw new IllegalArgumentException("Invalid projection-load text field: "+key);return value.getAsString();}
    static long integer(JsonObject request,String key){return integer(request.get(key));}
    private static long integer(JsonElement value){try{if(value==null||!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException();return value.getAsBigDecimal().longValueExact();}catch(RuntimeException e){throw new IllegalArgumentException("Projection load requires integer numeric fields");}}
}
