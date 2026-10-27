package dev.twob2tkit.chat.core;
import dev.twob2tkit.chat.ModConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;
class OnDemandConfigTest {
 @TempDir Path directory;
 @Test void preservesAutomaticBilingualDefault() {
  var config=ModConfig.load(directory.resolve("absent.json"));assertTrue(config.enabled);assertTrue(config.bilingual);assertFalse(config.onDemandTranslation);
 }
 @Test void onDemandChoiceSurvivesRestartWithoutChangingOtherPreferences() throws Exception {
  var path=directory.resolve("config.json");var config=new ModConfig();config.onDemandTranslation=true;config.targetLanguage="en";config.save(path);
  var loaded=ModConfig.load(path);assertTrue(loaded.onDemandTranslation);assertEquals("en",loaded.targetLanguage);assertTrue(loaded.bilingual);
 }
}
