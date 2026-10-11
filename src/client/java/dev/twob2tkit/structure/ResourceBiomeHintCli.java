package dev.twob2tkit.structure;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonParser;
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
        if(args.length!=5)throw new IllegalArgumentException("seed-file origin-x origin-z radius output-file");
        var saved=JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        if(!saved.has("crackedSeed")||saved.get("crackedSeed").isJsonNull())
            throw new IllegalStateException("No saved seed is available");
        long seed=saved.get("crackedSeed").getAsLong();
        int x=Integer.parseInt(args[1]),z=Integer.parseInt(args[2]),radius=Integer.parseInt(args[3]);
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var wanted=Set.of("minecraft:savanna","minecraft:savanna_plateau","minecraft:windswept_savanna");
        var candidates=new ArrayList<OverworldSnowLocator.Candidate>();
        int cursor=0,processed=0;boolean exhausted=false;
        do{
            var batch=OverworldSnowLocator.biomeCandidates(seed,x,z,radius,cursor,128,wanted);
            candidates.addAll(batch.candidates());processed+=batch.processed();
            cursor=batch.nextCursor();exhausted=batch.done();
        }while(candidates.size()<12&&!exhausted);
        candidates.sort(Comparator.comparingInt(OverworldSnowLocator.Candidate::distance));
        var result=new LinkedHashMap<String,Object>();
        result.put("source","saved_seed_vanilla_biome_sampler");result.put("hint_only",true);
        result.put("live_tree_verified",false);result.put("origin_x",x);result.put("origin_z",z);
        result.put("radius",radius);result.put("processed",processed);result.put("exhausted",exhausted);
        result.put("candidates",candidates);
        Path output=Path.of(args[4]);Files.createDirectories(output.toAbsolutePath().getParent());
        Files.writeString(output,new GsonBuilder().setPrettyPrinting().create().toJson(result));
        System.out.println("Biome hints="+candidates.size()+", sampled="+processed+", live verified=false");
    }
}
