package dev.twob2tkit.automation;

import java.util.regex.Pattern;

/** Only orientation mistakes in non-container observers; never a general wet-mining exemption. */
final class ProjectedComponentCorrectionPolicy {
    private static final Pattern OBSERVER=Pattern.compile(
        "Block\\{minecraft:observer\\}\\[facing=(down|up|north|south|west|east),powered=(true|false)\\]");
    static boolean observerCorrection(String observed,String projected){
        if(observed==null||projected==null)return false;
        var actual=OBSERVER.matcher(observed);var goal=OBSERVER.matcher(projected);
        return actual.matches()&&goal.matches()&&!actual.group(1).equals(goal.group(1));
    }
}
