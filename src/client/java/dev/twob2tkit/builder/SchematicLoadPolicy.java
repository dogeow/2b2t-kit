package dev.twob2tkit.builder;
/** LOADED only allocates a chunk; FILLED/RENDERED confirms schematic contents were copied. */
public final class SchematicLoadPolicy {
    private SchematicLoadPolicy(){}
    public static boolean ready(String state){return "FILLED".equals(state)||"RENDERED".equals(state);}
}
