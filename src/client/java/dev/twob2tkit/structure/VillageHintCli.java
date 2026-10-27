package dev.twob2tkit.structure;

import com.google.gson.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadType;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Offline vanilla placement/biome hints; every village and resident still needs live observation. */
public final class VillageHintCli {
    private record Candidate(int x,int z,String sampledBiome,int sampleY,int distance){}
    private VillageHintCli(){}
    public static void main(String[] args)throws Exception{
        if(args.length!=6)throw new IllegalArgumentException("verified-seed-file origin-x origin-z radius output coordinate-limit");
        var saved=JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        if(saved.get("schema").getAsInt()!=1||!saved.get("server").getAsString().equals("simpcraft.com")
                ||!saved.get("dimension").getAsString().equals("minecraft:overworld")
                ||saved.get("sample_count").getAsInt()<5||saved.get("sample_matches").getAsInt()!=saved.get("sample_count").getAsInt())
            throw new IllegalArgumentException("Original user seed and matched terrain calibration required");
        long seed=Long.parseLong(saved.get("seed").getAsString());
        int x=Integer.parseInt(args[1]),z=Integer.parseInt(args[2]),radius=Integer.parseInt(args[3]),limit=Integer.parseInt(args[5]);
        if(radius<64||radius>8192||!ResourceBiomeHintCli.insideBoundary(x,z,limit))throw new IllegalArgumentException("Bounded village hint radius and origin required");
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var villages=new HashSet<String>();
        for(String type:List.of("plains","desert","savanna","snowy","taiga"))readBiomeTag("minecraft:has_structure/village_"+type,villages,new HashSet<>());
        // These are the vanilla villages structure-set parameters read from the current game data.
        var placement=new RandomSpreadStructurePlacement(34,8,RandomSpreadType.LINEAR,10387312);
        int rx=Math.floorDiv(Math.floorDiv(x,16),34),rz=Math.floorDiv(Math.floorDiv(z,16),34),range=(int)Math.ceil(radius/544.0)+1;
        var candidates=new ArrayList<Candidate>();int sampled=0;
        for(int a=rx-range;a<=rx+range;a++)for(int b=rz-range;b<=rz+range;b++){
            var chunk=placement.getPotentialStructureChunk(seed,a*34,b*34);int px=chunk.getMiddleBlockX(),pz=chunk.getMiddleBlockZ();
            int distance=(int)Math.round(Math.hypot((long)px-x,(long)pz-z));
            if(distance>radius||!ResourceBiomeHintCli.insideBoundary(px,pz,limit))continue;
            String biome=OverworldSnowLocator.biomeAt(seed,px,64,pz);sampled++;
            if(villages.contains(biome))candidates.add(new Candidate(px,pz,biome,64,distance));
        }
        candidates.sort(Comparator.comparingInt(Candidate::distance));
        var result=new LinkedHashMap<String,Object>();result.put("hint_only",true);result.put("live_village_verified",false);
        result.put("live_residents_verified",false);result.put("expected_generation_version",saved.get("generation_version").getAsString());
        result.put("sampler_and_placement_data_version","26.2");result.put("sample_y",64);
        result.put("source","calibrated_user_seed_vanilla_random_spread_and_surface_biome_hint");
        result.put("origin",List.of(x,z));result.put("radius",radius);result.put("coordinate_limit",limit);
        result.put("sampled_placement_candidates",sampled);result.put("candidates",candidates.stream().limit(24).toList());
        Path output=Path.of(args[4]);Files.createDirectories(output.toAbsolutePath().getParent());
        Files.writeString(output,new GsonBuilder().setPrettyPrinting().create().toJson(result));
        System.out.println("Village hints="+candidates.size()+", placement samples="+sampled+", live verified=false");
    }
    private static void readBiomeTag(String key,Set<String> values,Set<String> visited)throws Exception{
        if(!visited.add(key))return;String[] name=key.split(":",2);
        String resource="data/"+name[0]+"/tags/worldgen/biome/"+name[1]+".json";
        try(var stream=VillageHintCli.class.getClassLoader().getResourceAsStream(resource)){
            if(stream==null)throw new IllegalStateException("Vanilla village biome tag unavailable");
            for(var entry:JsonParser.parseString(new String(stream.readAllBytes(),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonArray("values")){
                String id=entry.isJsonObject()?entry.getAsJsonObject().get("id").getAsString():entry.getAsString();
                if(id.startsWith("#"))readBiomeTag(id.substring(1),values,visited);else values.add(id);
            }
        }
    }
}
