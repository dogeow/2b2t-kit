package dev.twob2tkit.automation;

import java.util.Locale;

/** Chooses the immutable host-owned return target for one material session. */
final class MaterialReturnTargetPolicy {
    record Home(double x,double z,double cruiseY,String dimension) {}
    record Target(double x,double z,double cruiseY,String dimension,String source) {}

    private MaterialReturnTargetPolicy() {}

    static Target choose(Home home,String dimension,
            double originX,double originY,double originZ) {
        String current=normalizeDimension(dimension);
        boolean saved=eligible(home,current);
        double x=saved?home.x():originX;
        double z=saved?home.z():originZ;
        double cruiseY=safeCruiseY(saved?home.cruiseY():originY,200);
        return new Target(x,z,cruiseY,current,saved?"saved_home":"search_origin");
    }

    private static boolean eligible(Home home,String dimension) {
        if(home==null||!safeHorizontal(home.x(),home.z()))return false;
        String stored=normalizeDimension(home.dimension());
        return stored.isEmpty()||stored.equals(dimension);
    }

    private static double safeCruiseY(double requested,double fallback) {
        double value=Double.isFinite(requested)?requested:fallback;
        if(!Double.isFinite(value))value=200;
        return Math.max(160,Math.min(316,value));
    }

    private static boolean safeHorizontal(double x,double z) {
        return Double.isFinite(x)&&Double.isFinite(z)
            &&Math.abs(x)<=29_999_984&&Math.abs(z)<=29_999_984;
    }

    private static String normalizeDimension(String raw) {
        if(raw==null||raw.isBlank())return "";
        String value=raw.trim().toLowerCase(Locale.ROOT);
        if(value.contains("nether"))return "minecraft:the_nether";
        if(value.endsWith("the_end")||value.equals("end"))return "minecraft:the_end";
        if(value.endsWith("overworld")||value.equals("world"))return "minecraft:overworld";
        return raw.trim();
    }
}
