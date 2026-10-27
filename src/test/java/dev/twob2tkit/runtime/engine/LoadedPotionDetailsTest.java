package dev.twob2tkit.runtime.engine;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class LoadedPotionDetailsTest {
    @Test void unknown_or_oversized_menu_is_not_complete(){
        assertFalse(LoadedPotionDetails.supportedMenuSize(-1));assertFalse(LoadedPotionDetails.supportedMenuSize(91));
        assertTrue(LoadedPotionDetails.supportedMenuSize(46));assertTrue(LoadedPotionDetails.supportedMenuSize(63));assertTrue(LoadedPotionDetails.supportedMenuSize(90));
    }
    @Test void only_an_actual_nonempty_potion_observation_is_retained(){
        var frame=new JsonObject();assertFalse(LoadedPotionDetails.retain(frame));
        var rows=new JsonArray();frame.add("potions",rows);assertFalse(LoadedPotionDetails.retain(frame));
        var potion=new JsonObject();potion.addProperty("item","minecraft:splash_potion");rows.add(potion);
        assertTrue(LoadedPotionDetails.retain(frame));
    }
}
