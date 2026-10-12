package dev.twob2tkit.storage;
import dev.twob2tkit.KitConfig;
import com.google.gson.*;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionSupplyRegistryTest {
    private KitConfig.StorageSnapshot record(){var r=new KitConfig.StorageSnapshot();r.server="simpcraft.com";r.dimension="minecraft:overworld";r.status="active";r.x=10;r.y=64;r.z=20;return r;}
    private ProjectionSupplyRegistry.Update set(List<KitConfig.ProjectionSupplySource> sources,KitConfig.StorageSnapshot r,boolean enabled){return ProjectionSupplyRegistry.set(sources,"Simpcraft.com:25565","","minecraft:overworld",r,enabled);}
    @Test void repeatedExplicitSetIsIdempotentAndDuplicateEntriesAreRemoved(){
        var r=record();var first=set(null,r,true);assertTrue(first.changed());assertEquals(1,first.sources().size());
        var second=set(first.sources(),r,true);assertFalse(second.changed());assertEquals(1,second.sources().size());
        var duplicates=set(List.of(first.sources().getFirst(),first.sources().getFirst()),r,true);
        assertTrue(duplicates.changed());assertEquals(1,duplicates.sources().size());
        var disabled=set(duplicates.sources(),r,false);assertTrue(disabled.changed());assertTrue(disabled.sources().isEmpty());
        assertFalse(set(disabled.sources(),r,false).changed());assertEquals(0,r.lastSeenEpochMillis);
    }
    @Test void ForeignRecordsCannotBeRegisteredAndUnrelatedPermissionsSurvive(){
        var r=record();var source=set(null,r,true).sources().getFirst();source.worldId="another-save";
        var current=set(List.of(source),r,true);assertEquals(2,current.sources().size());assertSame(source,current.sources().getFirst());
        for(String field:List.of("server","dimension","world")){
            var foreign=record();if(field.equals("server"))foreign.server="other.example";
            else if(field.equals("dimension"))foreign.dimension="minecraft:the_nether";else foreign.worldId="other-save";
            assertThrows(IllegalArgumentException.class,()->set(List.of(source),foreign,true));
        }
    }
    @Test void MissingContainerCannotBeEnabledButItsPermissionCanBeRevoked(){
        var r=record();var sources=set(null,r,true).sources();r.status="missing";
        assertThrows(IllegalArgumentException.class,()->set(sources,r,true));assertTrue(set(sources,r,false).sources().isEmpty());
    }
    private JsonObject request(){return JsonParser.parseString("{\"id\":\"supply-1\",\"op\":\"projection_supply_set\",\"pos\":[10,64,20],\"enabled\":true}").getAsJsonObject();}
    @Test void ProtocolRequiresExactBooleanCoordinatesAndCannotCarryActions(){
        assertTrue(ProjectionSupplyProtocol.parse(request()).enabled());
        for(JsonElement enabled:List.of(new JsonPrimitive("true"),new JsonPrimitive(1),JsonNull.INSTANCE)){
            var r=request();r.add("enabled",enabled);assertThrows(IllegalArgumentException.class,()->ProjectionSupplyProtocol.parse(r));
        }
        for(String pos:List.of("[10.5,64,20]","[true,64,20]","[\"10\",64,20]","[10,64]","[30000001,64,20]","[-2147483648,64,20]")){
            var r=request();r.add("pos",JsonParser.parseString(pos));assertThrows(IllegalArgumentException.class,()->ProjectionSupplyProtocol.parse(r));
        }
        for(String field:List.of("command","task_session","materials")){var r=request();r.addProperty(field,"anything");assertThrows(IllegalArgumentException.class,()->ProjectionSupplyProtocol.parse(r));}
    }
}
