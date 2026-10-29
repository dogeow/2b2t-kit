package dev.twob2tkit.automation;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionSelectionPolicyTest {
    JsonObject request(){var r=new JsonObject();r.addProperty("id","select-1");r.addProperty("op","projection_select");r.addProperty("schema",1);r.addProperty("manual_start",true);r.addProperty("placement_index",64);r.addProperty("expected_registry","a".repeat(64));r.addProperty("expected_fingerprint","b".repeat(64));return r;}
    @Test void explicitSelectionHasAnIndependentStrictEnvelope(){assertDoesNotThrow(()->ProjectionSelectionPolicy.envelope(request()));}
    @Test void importParametersCannotBeSmuggledIntoExistingSelection(){var r=request();r.addProperty("file","new.litematic");assertThrows(IllegalArgumentException.class,()->ProjectionSelectionPolicy.envelope(r));}
    @Test void malformedOrNonExplicitProofCannotSelectAnything(){
        for(String key:new String[]{"manual_start","placement_index","expected_registry","expected_fingerprint"}){
            var r=request();r.remove(key);assertThrows(IllegalArgumentException.class,()->ProjectionSelectionPolicy.envelope(r));
        }
        for(double index:new double[]{-1,1024,.5}){var r=request();r.addProperty("placement_index",index);assertThrows(IllegalArgumentException.class,()->ProjectionSelectionPolicy.envelope(r));}
        var r=request();r.addProperty("manual_start","true");assertThrows(IllegalArgumentException.class,()->ProjectionSelectionPolicy.envelope(r));
    }
}
