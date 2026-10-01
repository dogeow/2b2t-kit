package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;

/** Exact unsigned packed map pixels; no synthetic pixels or refresh claims. */
final class MapAuditCodec {
    static final int PIXELS=128*128;
    private MapAuditCodec() {}

    static JsonObject colors(byte[] source) {
        if(source==null||source.length!=PIXELS)
            throw new IllegalStateException("Loaded map does not contain 16384 packed colors");
        byte[] bytes=source.clone();int none=0;
        for(byte color:bytes)if(((color&255)>>>2)==0)none++;
        var out=new JsonObject();out.addProperty("width",128);out.addProperty("height",128);
        out.addProperty("packed_color_count",PIXELS);out.addProperty("packed_color_encoding","base64-u8");
        out.addProperty("packed_colors",Base64.getEncoder().encodeToString(bytes));
        try{out.addProperty("colors_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));}
        catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
        out.addProperty("map_color_none_pixels",none);
        out.addProperty("pixel_order","index=z*128+x; x east/right, z south/down");
        out.addProperty("pixel_format","unsigned byte: map_color_id=byte>>>2, brightness=byte&3");
        out.addProperty("source","current_loaded_client_map_data");
        out.addProperty("freshness_verified",false);
        return out;
    }
}
