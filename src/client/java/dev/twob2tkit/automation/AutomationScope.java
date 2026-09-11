package dev.twob2tkit.automation;
import java.util.Locale;
/** Pure admission rules shared by live scripts and regression tests. */
public final class AutomationScope {
    private AutomationScope() {}
    public static boolean sameServer(String current,String expected){
        if(current==null || expected==null || expected.isBlank())return false;
        return normalize(current).equals(normalize(expected));
    }
    private static String normalize(String s){return s.trim().toLowerCase(Locale.ROOT).replaceFirst(":25565$","");}
    public static boolean nearSite(double dx,double dz){return Double.isFinite(dx) && Double.isFinite(dz) && Math.hypot(dx,dz)<=512;}
}
