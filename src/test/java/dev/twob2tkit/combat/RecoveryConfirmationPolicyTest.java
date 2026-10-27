package dev.twob2tkit.combat;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RecoveryConfirmationPolicyTest {
    JsonObject grant(){return JsonParser.parseString("{\"confirmed_by_user\":true,\"authorization_channel\":\"human_chat\",\"authorization_reference\":\"user-message-1\",\"authorization_text\":\"已恢复，你操作\",\"confirmed_hold_time\":100,\"confirmation_recorded_at\":120,\"world_session\":\"w\",\"expected_revision\":5,\"expires_at\":1000}").getAsJsonObject();}
    void allow(JsonObject request){RecoveryConfirmationPolicy.require(request,200,100,"w",5,true,20,20,true,true,true);}
    @Test void directHumanConfirmationMayPersistForTheSameIncident(){assertDoesNotThrow(()->allow(grant()));var r=grant();r.addProperty("confirmation_recorded_at",101);assertDoesNotThrow(()->allow(r));}
    @Test void automationOldIncidentsAndIncompleteGrantsNeverQualify(){
        for(String key:new String[]{"confirmed_by_user","authorization_channel","authorization_reference","authorization_text","confirmed_hold_time","confirmation_recorded_at"}){
            var r=grant();r.remove(key);assertThrows(IllegalStateException.class,()->allow(r),key);
        }
        for(String value:new String[]{"automation","goal","game_ui"}){var r=grant();r.addProperty("authorization_channel",value);assertThrows(IllegalStateException.class,()->allow(r));}
        for(long stamp:new long[]{0,99,101}){var r=grant();r.addProperty("confirmed_hold_time",stamp);assertThrows(IllegalStateException.class,()->allow(r));}
        for(long stamp:new long[]{99,201}){var r=grant();r.addProperty("confirmation_recorded_at",stamp);assertThrows(IllegalStateException.class,()->allow(r));}
        var bool=grant();bool.addProperty("confirmed_by_user","true");assertThrows(IllegalStateException.class,()->allow(bool));
    }
    @Test void currentWorldRevisionAndRequestExpiryAreMandatory(){
        var world=grant();world.addProperty("world_session","old");assertThrows(IllegalStateException.class,()->allow(world));
        var revision=grant();revision.addProperty("expected_revision",4);assertThrows(IllegalStateException.class,()->allow(revision));
        for(long expiry:new long[]{199,15201}){var r=grant();r.addProperty("expires_at",expiry);assertThrows(IllegalStateException.class,()->allow(r));}
    }
    @Test void offlineLowHealthManualControlUnsafeUiAndRecentDamageStayLocked(){
        assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.require(grant(),200,100,"w",5,false,20,20,true,true,true));
        for(double health:new double[]{0,10.7,17.9,Double.NaN,Double.POSITIVE_INFINITY})assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.require(grant(),200,100,"w",5,true,health,20,true,true,true));
        for(int mode=0;mode<3;mode++){int m=mode;assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.require(grant(),200,100,"w",5,true,20,20,m!=0,m!=1,m!=2));}
        assertDoesNotThrow(()->RecoveryConfirmationPolicy.require(grant(),200,100,"w",5,true,18,8,true,true,true));
    }
    @Test void nativeRecordKeepsTheHumanChannelAndCannotAcknowledgeANewerIncident(){
        var record=new JsonObject();RecoveryConfirmationPolicy.copyGrant(record,grant(),200);
        assertEquals("explicit_chat",record.get("cleared_by").getAsString());assertTrue(RecoveryConfirmationPolicy.explicitAck(record,100));
        record.addProperty("cleared_at",500);assertFalse(RecoveryConfirmationPolicy.explicitAck(record,101));
        record.addProperty("authorization_channel","goal");assertFalse(RecoveryConfirmationPolicy.explicitAck(record,100));
    }
    @Test void otherServersDimensionsAndPlayersCannotClearTheIncident(){
        var origin=JsonParser.parseString("{\"server\":\"SIMPCraft.com:25565\",\"dimension\":\"minecraft:overworld\",\"player\":\"p\"}").getAsJsonObject();
        assertDoesNotThrow(()->RecoveryConfirmationPolicy.requireOrigin(origin,"simpcraft.com","minecraft:overworld","p"));
        assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.requireOrigin(origin,"other","minecraft:overworld","p"));
        assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.requireOrigin(origin,"simpcraft.com","minecraft:the_nether","p"));
        assertThrows(IllegalStateException.class,()->RecoveryConfirmationPolicy.requireOrigin(origin,"simpcraft.com","minecraft:overworld","other"));
    }
    @Test void onlyValidatedNativeHumanMetadataSatisfiesTheMaterialHold(){
        var record=new JsonObject();RecoveryConfirmationPolicy.copyGrant(record,grant(),200);
        assertFalse(MaterialHealthHoldPolicy.active(JsonParser.parseString("{\"active\":true,\"time\":100}"),record));
        assertTrue(MaterialHealthHoldPolicy.active(JsonParser.parseString("{\"active\":true,\"time\":101}"),record));
        record.remove("confirmation_recorded_at");assertTrue(MaterialHealthHoldPolicy.active(JsonParser.parseString("{\"active\":true,\"time\":100}"),record));
    }
}
