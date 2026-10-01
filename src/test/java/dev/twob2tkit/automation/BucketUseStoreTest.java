package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class BucketUseStoreTest {
    @TempDir Path root;
    private Path cell(){return BucketUseStore.path(root,"server","minecraft:overworld",1,63,2);}
    private static JsonObject receipt(boolean confirmed){var r=new JsonObject();r.addProperty("confirmed",confirmed);return r;}
    @Test void uncertainClaimBlocksAnotherIdAndAnotherOperation()throws Exception {
        var r=receipt(false);r.addProperty("request_id","a");r.addProperty("operation","bucket_fill");BucketUseStore.claim(cell(),r);
        var next=receipt(false);next.addProperty("request_id","b");next.addProperty("operation","bucket_place");
        assertThrows(IllegalStateException.class,()->BucketUseStore.claim(cell(),next));
    }
    @Test void confirmedTerminalAllowsANewExplicitCycle()throws Exception {
        BucketUseStore.claim(cell(),receipt(false));BucketUseStore.update(cell(),receipt(true));BucketUseStore.requireAvailable(cell());
        BucketUseStore.claim(cell(),receipt(false));assertThrows(IllegalStateException.class,()->BucketUseStore.requireAvailable(cell()));
    }
    @Test void crashLeavingEmptyInodeBlocksReplay()throws Exception {
        Files.createDirectories(cell().getParent());Files.createFile(cell());assertThrows(RuntimeException.class,()->BucketUseStore.requireAvailable(cell()));
    }
    @Test void missingOrNonBooleanConfirmationNeverReopens()throws Exception {
        var bad=new JsonObject();bad.addProperty("confirmed","true");BucketUseStore.claim(cell(),bad);
        assertThrows(IllegalStateException.class,()->BucketUseStore.requireAvailable(cell()));
        BucketUseStore.update(cell(),new JsonObject());assertThrows(IllegalStateException.class,()->BucketUseStore.requireAvailable(cell()));
    }
    @Test void claimPersistsAcrossARecreatedPathObject()throws Exception {
        BucketUseStore.claim(cell(),receipt(false));var reopened=BucketUseStore.path(root,"server","minecraft:overworld",1,63,2);
        assertThrows(IllegalStateException.class,()->BucketUseStore.requireAvailable(reopened));
    }
    @Test void equivalentServerSpellingCannotBypassAnUnknownClaim()throws Exception {
        var alias=BucketUseStore.path(root," SERVER:25565 ","minecraft:overworld",1,63,2);
        assertEquals(cell(),alias);BucketUseStore.claim(cell(),receipt(false));
        assertThrows(IllegalStateException.class,()->BucketUseStore.claim(alias,receipt(false)));
    }
    @Test void serverDimensionAndCellAreSeparated(){
        assertNotEquals(cell(),BucketUseStore.path(root,"server2","minecraft:overworld",1,63,2));
        assertNotEquals(cell(),BucketUseStore.path(root,"server","minecraft:the_nether",1,63,2));
        assertNotEquals(cell(),BucketUseStore.path(root,"server","minecraft:overworld",1,63,3));
        assertEquals(root.resolve("bucket-use-claims-v1"),cell().getParent());
    }
    @Test void absentClaimCannotBeUpdated(){assertThrows(IllegalStateException.class,()->BucketUseStore.update(cell(),receipt(true)));}
}
