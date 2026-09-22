package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class QuietLogoutWindowTest {
 @Test void finishingDuringBowDefenseNeverCountsAsQuiet(){var p=new QuietLogoutWindow();p.reset(1_000);assertFalse(p.ready(80_000,true,0));assertFalse(p.ready(139_999,false,0));assertTrue(p.ready(140_000,false,0));}
 @Test void aNewHitRestartsTheWindowEvenIfHealthRecovered(){var p=new QuietLogoutWindow();p.reset(1_000);assertFalse(p.ready(120_000,false,110_000));assertTrue(p.ready(170_000,false,110_000));}
 @Test void aNewSessionDoesNotInheritAnOlderQuietWindow(){var p=new QuietLogoutWindow();p.reset(100_000);assertFalse(p.ready(100_001,false,0));assertTrue(p.ready(160_000,false,0));}
}
