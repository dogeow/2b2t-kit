package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class MapAuditCodecTest {
    @Test void exactPackedUnsignedBytesAndOrderRoundTripWithoutInventingPixels()throws Exception {
        byte[] original=new byte[16384];
        for(int i=0;i<original.length;i++)original[i]=(byte)(i%256);
        var encoded=MapAuditCodec.colors(original);
        assertArrayEquals(original,Base64.getDecoder().decode(encoded.get("packed_colors").getAsString()));
        assertEquals(16384,encoded.get("packed_color_count").getAsInt());
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original)),encoded.get("colors_sha256").getAsString());
        assertEquals(256,encoded.get("map_color_none_pixels").getAsInt());
        assertFalse(encoded.get("freshness_verified").getAsBoolean());
    }
    @Test void missingOrShortClientBuffersAreErrorsRatherThanBlankSyntheticMaps() {
        assertThrows(IllegalStateException.class,()->MapAuditCodec.colors(null));
        assertThrows(IllegalStateException.class,()->MapAuditCodec.colors(new byte[16383]));
    }
}
