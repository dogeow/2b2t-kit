package dev.twob2tkit.structure;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonParser;
import com.google.gson.JsonObject;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Set;

/** Offline hints only: never exposes the saved seed or claims server/tree verification. */
public final class ResourceBiomeHintCli {
    private ResourceBiomeHintCli(){}
    public static void main(String[] args)throws Exception{
        if(args.length<5||args.length>7)throw new IllegalArgumentException("seed-file origin-x origin-z radius output-file [biome-ids] [coordinate-limit]");
        var saved=JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        if(!saved.has("crackedSeed")||saved.get("crackedSeed").isJsonNull())
            throw new IllegalStateException("No saved seed is available");
        long seed=saved.get("crackedSeed").getAsLong();
        if(!seedHashMatches(saved,seed))throw new IllegalStateException("Saved seed is not matched to the current server hash; use verified versioned sampling");
        int x=Integer.parseInt(args[1]),z=Integer.parseInt(args[2]),radius=Integer.parseInt(args[3]);
        int limit=args.length==7?Integer.parseInt(args[6]):30_000_000;
        if(limit<=32||limit>30_000_000||!insideBoundary(x,z,limit))throw new IllegalArgumentException("Origin outside the guarded world boundary");
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var wanted=parseBiomes(args.length>=6?args[5]:"");
        var candidates=new ArrayList<OverworldSnowLocator.Candidate>();
        int cursor=0,processed=0;boolean exhausted=false;
        do{
            var batch=OverworldSnowLocator.biomeCandidates(seed,x,z,radius,cursor,128,wanted);
            candidates.addAll(batch.candidates().stream().filter(c->insideBoundary(c.x(),c.z(),limit)).toList());processed+=batch.processed();
            cursor=batch.nextCursor();exhausted=batch.done();
        }while(candidates.size()<12&&!exhausted);
        candidates.sort(Comparator.comparingInt(OverworldSnowLocator.Candidate::distance));
        var result=new LinkedHashMap<String,Object>();
        result.put("source","saved_seed_vanilla_biome_sampler");result.put("hint_only",true);
        result.put("live_tree_verified",false);result.put("origin_x",x);result.put("origin_z",z);
        result.put("wanted_biomes",wanted);result.put("live_blocks_verified",false);result.put("inventory_credit",0);
        result.put("radius",radius);result.put("processed",processed);result.put("exhausted",exhausted);
        result.put("candidates",candidates);
        Path output=Path.of(args[4]);Files.createDirectories(output.toAbsolutePath().getParent());
        Files.writeString(output,new GsonBuilder().setPrettyPrinting().create().toJson(result));
        System.out.println("Biome hints="+candidates.size()+", sampled="+processed+", live verified=false");
    }

    static boolean seedHashMatches(JsonObject saved,long seed){
        try{return saved.has("hasHashedSeed")&&saved.get("hasHashedSeed").getAsBoolean()
            &&saved.has("hashedSeed")&&saved.get("hashedSeed").getAsLong()==net.minecraft.world.level.biome.BiomeManager.obfuscateSeed(seed);}
        catch(RuntimeException malformed){return false;}
    }
    static boolean calibrationAllowsHints(boolean hashMatched,int sampled,int matched,int landSamples){
        return sampled>=5&&matched==sampled&&(hashMatched||landSamples>=2);
    }
    static boolean insideBoundary(int x,int z,int limit){
        return limit>32&&Math.abs((long)x)<(long)limit-32&&Math.abs((long)z)<(long)limit-32;
    }

    static Set<String> parseBiomes(String value){
        if(value.isEmpty())return Set.of("minecraft:savanna","minecraft:savanna_plateau","minecraft:windswept_savanna");
        var wanted=new java.util.TreeSet<String>();
        for(String id:value.split(",",-1)){
            if(!id.matches("minecraft:[a-z_]+"))throw new IllegalArgumentException("Use explicit vanilla biome IDs");
            wanted.add(id);
        }
        if(wanted.size()>32)throw new IllegalArgumentException("At most 32 biome IDs");
        return java.util.Collections.unmodifiableSet(wanted);
    }
}
