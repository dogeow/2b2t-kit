package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class PrinterExternalModeHistoryTest {
    @Test void initialModeAndOwnedChangesDoNotBecomeUserRequests(){
        var h=new PrinterExternalModeHistory();h.observe(true);h.written(false);h.observe(false);
        h.written(true);h.observe(true);h.written(false);h.observe(false);
        assertEquals(0,h.revision());assertNull(h.lastExternal());
    }
    @Test void newerUserChoiceSurvivesSubsequentOwnedPause(){
        var h=new PrinterExternalModeHistory();h.observe(true);h.written(false);
        h.observe(true);assertEquals(1,h.revision());assertEquals(Boolean.TRUE,h.lastExternal());
        h.written(false);h.observe(false);
        assertEquals(1,h.revision());assertEquals(Boolean.TRUE,h.lastExternal());
        h.observe(true);h.observe(false);
        assertEquals(3,h.revision());assertEquals(Boolean.FALSE,h.lastExternal());
    }
    @Test void synchronousSettingCallbacksDuringOwnedWritesAreNotUserChanges(){
        var h=new PrinterExternalModeHistory();h.observe(true);h.beginWrite();
        h.observe(false);h.written(false);h.endWrite();h.observe(false);
        assertEquals(0,h.revision());assertNull(h.lastExternal());
        h.observe(true);assertEquals(1,h.revision());
    }
    @Test void nativeModeHandoffCannotPreemptAnOwnerOrWriteWorldState()throws Exception{
        var bridge=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        int a=bridge.indexOf("}else if(command.equals(\"printer_mode\")){");
        int b=bridge.indexOf("}else if(command.equals(\"professional_print\"))",a);var handoff=bridge.substring(a,b);
        for(String required:new String[]{"nativeMaterialOwner!=null","supervisionLease!=null","ProfessionalPrinter.owned()",
                "KitKeys.manualMovementDown(c)","expected_external_revision","placement_key","expected_enabled"})assertTrue(handoff.contains(required));
        for(String forbidden:new String[]{"setBlock(","useItem(","emergencyStop(","guardScope=null"})assertFalse(handoff.contains(forbidden));
        var printer=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProfessionalPrinter.java"));
        assertTrue(printer.contains("externalModeHistory.revision()!=expectedExternalRevision"));
        assertTrue(printer.contains("externalModeHistory.written(value)"));
    }
}
