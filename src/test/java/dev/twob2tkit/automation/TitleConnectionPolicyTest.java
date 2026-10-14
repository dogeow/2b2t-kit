package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TitleConnectionPolicyTest {
    void require(boolean disconnected, boolean title, boolean idle, boolean held, String world,
                 long revision, long expiry, String account) {
        TitleConnectionPolicy.require(disconnected,title,idle,held,"",world,2,revision,
            1_000,expiry,"likunyan",account);
    }
    @Test void currentIdleTitleAccountCanConnectNormally() {
        assertDoesNotThrow(()->require(true,true,true,false,"",2,5_000,"likunyan"));
    }
    @Test void loadedWorldOtherScreenBusyTaskAndSafetyHoldNeverConnectOrQuit() {
        assertThrows(IllegalStateException.class,()->require(false,true,true,false,"",2,5_000,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,false,true,false,"",2,5_000,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,false,false,"",2,5_000,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,true,true,"",2,5_000,"likunyan"));
    }
    @Test void staleWorldRevisionExpiredOrDifferentAccountIsRejected() {
        assertThrows(IllegalStateException.class,()->require(true,true,true,false,"old",2,5_000,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,true,false,"",1,5_000,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,true,false,"",2,999,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,true,false,"",2,16_001,"likunyan"));
        assertThrows(IllegalStateException.class,()->require(true,true,true,false,"",2,5_000,"other"));
    }
}
