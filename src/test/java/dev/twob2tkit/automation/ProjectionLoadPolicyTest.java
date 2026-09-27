package dev.twob2tkit.automation;
import com.google.gson.*;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionLoadPolicyTest {
    @TempDir Path game;
    private JsonObject request()throws Exception{
        Files.createDirectories(game.resolve("schematics/courtyard"));Files.write(game.resolve("schematics/courtyard/庭院.litematic"),new byte[]{1,2,3});
        return JsonParser.parseString("{\"schema\":1,\"id\":\"load-one\",\"op\":\"projection_load\",\"file\":\"courtyard/庭院.litematic\",\"name\":\"庭院独立施工\",\"origin\":[761000,64,797800],\"rotation\":\"CLOCKWISE_90\",\"mirror\":\"NONE\",\"manual_start\":true}").getAsJsonObject();
    }
    @Test void explicitUnicodeLocalPathAndTransformArePreserved()throws Exception{
        var parsed=ProjectionLoadPolicy.parse(game,request());assertEquals(game.resolve("schematics/courtyard/庭院.litematic").toRealPath(),parsed.file());
        assertEquals(new BlockPos(761000,64,797800),parsed.origin());assertEquals("CLOCKWISE_90",parsed.rotation());assertTrue(parsed.regions().isEmpty());
    }
    @Test void parentsAbsolutePathsForeignSymlinksAndWrongExtensionsAreRejected()throws Exception{
        var valid=request();Path outside=game.resolve("outside.litematic");Files.writeString(outside,"private");
        Files.createSymbolicLink(game.resolve("schematics/escape.litematic"),outside);
        for(String path:List.of("../outside.litematic",outside.toString(),"escape.litematic","courtyard/data.json")){
            var bad=valid.deepCopy();bad.addProperty("file",path);assertThrows(Exception.class,()->ProjectionLoadPolicy.parse(game,bad),path);
        }
    }
    @Test void emptyOrOversizedSchematicFileNeverReachesLitematica()throws Exception{
        request();Path file=game.resolve("schematics/empty.litematic");Files.write(file,new byte[0]);
        assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.resolve(game,"empty.litematic"));
        try(var access=new java.io.RandomAccessFile(file.toFile(),"rw")){access.setLength(ProjectionLoadPolicy.MAX_FILE_BYTES+1);}
        assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.resolve(game,"empty.litematic"));
    }
    @Test void schemaNumbersConsentAndRegionNamesAreStrict()throws Exception{
        var original=request();
        for(var change:Map.of("schema",new JsonPrimitive(2),"manual_start",new JsonPrimitive("true"),"rotation",new JsonPrimitive("north"),"mirror",new JsonPrimitive("east"),"command",new JsonPrimitive("/fill"),"task_session",new JsonPrimitive("foreign")) .entrySet()){
            var bad=original.deepCopy();bad.add(change.getKey(),change.getValue());assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.parse(game,bad));
        }
        var fractional=original.deepCopy();fractional.add("origin",JsonParser.parseString("[1,64.5,2]"));assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.parse(game,fractional));
        for(String regions:List.of("[]","[\"A\",\"A\"]","[12]")){var bad=original.deepCopy();bad.add("regions",JsonParser.parseString(regions));assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.parse(game,bad));}
        var good=original.deepCopy();good.add("regions",JsonParser.parseString("[\"Pool\",\"Fence\"]"));assertEquals(List.of("Pool","Fence"),ProjectionLoadPolicy.parse(game,good).regions());
    }
    @Test void idleWorldScopeAndSafetyNeverAcceptStaleOrBusyWrites(){
        assertDoesNotThrow(()->ProjectionLoadPolicy.scope(true,true,true,false,true,true,"w","w",4,4,6000,1000));
        boolean[][] cases={{false,true,true,false,true,true},{true,false,true,false,true,true},{true,true,false,false,true,true},{true,true,true,true,true,true},{true,true,true,false,false,true},{true,true,true,false,true,false}};
        for(var c:cases)assertThrows(IllegalStateException.class,()->ProjectionLoadPolicy.scope(c[0],c[1],c[2],c[3],c[4],c[5],"w","w",4,4,6000,1000));
        assertThrows(IllegalStateException.class,()->ProjectionLoadPolicy.scope(true,true,true,false,true,true,"old","w",4,4,6000,1000));
        assertThrows(IllegalStateException.class,()->ProjectionLoadPolicy.scope(true,true,true,false,true,true,"w","w",3,4,6000,1000));
        for(long expiry:new long[]{999,16001})assertThrows(IllegalStateException.class,()->ProjectionLoadPolicy.scope(true,true,true,false,true,true,"w","w",4,4,expiry,1000));
    }
    @Test void signedRegionSizesAndBoundsAreLimitedWithoutOverflow(){
        assertEquals(600,ProjectionLoadPolicy.volume(-10,20,3));
        for(int[] values:List.of(new int[]{0,1,1},new int[]{100001,1,1},new int[]{1000,1000,1000},new int[]{Integer.MIN_VALUE,1,1}))assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.volume(values[0],values[1],values[2]));
    }
    @Test void compressedBombAndWrongNbtRootAreRejectedBeforeDecode()throws Exception{
        Path file=game.resolve("compressed.litematic");
        try(var gzip=new java.util.zip.GZIPOutputStream(Files.newOutputStream(file))){gzip.write(10);gzip.write(new byte[100]);}
        assertEquals(101,ProjectionLoadPolicy.decodedSize(file,1024));assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.decodedSize(file,64));
        try(var gzip=new java.util.zip.GZIPOutputStream(Files.newOutputStream(file))){gzip.write(8);gzip.write(new byte[20]);}
        assertThrows(IllegalArgumentException.class,()->ProjectionLoadPolicy.decodedSize(file,1024));
    }
}
