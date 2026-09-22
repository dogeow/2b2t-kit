package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class CraftConfirmationTest {
    @Test void serverCanConfirmAfterTheOldFourTickWindowWithoutAnotherClick(){
        var confirmation=new CraftConfirmation();
        for(int i=0;i<12;i++)assertFalse(confirmation.ready(false,"pending"));
        assertTrue(confirmation.ready(true,"pending"));
    }
    @Test void anUnconfirmedOperationHasABoundedWaitAndEachClickGetsANewWindow(){
        var c=new CraftConfirmation();for(int i=0;i<80;i++)assertFalse(c.ready(false,"pending"));
        assertThrows(IllegalStateException.class,()->c.ready(false,"pending"));
        c.reset();assertFalse(c.ready(false,"new click"));assertTrue(c.ready(true,"new click"));
    }
}
