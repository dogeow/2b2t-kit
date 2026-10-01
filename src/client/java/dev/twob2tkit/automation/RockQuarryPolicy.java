package dev.twob2tkit.automation;

import java.util.Set;

/** Bounded dry excavation policy, separate from the existing surface sand quarry. */
final class RockQuarryPolicy {
    static final int BUFFER = 3;
    // Current vanilla OreVeinifier.IRON limits, not a general building-block whitelist.
    static final int RAW_IRON_BLOCK_MIN_Y = -60, RAW_IRON_BLOCK_MAX_Y = -8;
    private static final Set<String> NATURAL = Set.of(
        "minecraft:stone", "minecraft:deepslate", "minecraft:granite", "minecraft:diorite",
        "minecraft:andesite", "minecraft:tuff", "minecraft:calcite", "minecraft:dripstone_block",
        "minecraft:dirt", "minecraft:grass_block", "minecraft:coarse_dirt", "minecraft:rooted_dirt",
        "minecraft:podzol", "minecraft:mycelium", "minecraft:clay", "minecraft:raw_iron_block",
        "minecraft:coal_ore", "minecraft:deepslate_coal_ore", "minecraft:iron_ore", "minecraft:deepslate_iron_ore",
        "minecraft:copper_ore", "minecraft:deepslate_copper_ore", "minecraft:gold_ore", "minecraft:deepslate_gold_ore",
        "minecraft:redstone_ore", "minecraft:deepslate_redstone_ore", "minecraft:lapis_ore", "minecraft:deepslate_lapis_ore",
        "minecraft:diamond_ore", "minecraft:deepslate_diamond_ore", "minecraft:emerald_ore", "minecraft:deepslate_emerald_ore");
    private static final Set<String> ITEMS = Set.of("minecraft:cobblestone", "minecraft:cobbled_deepslate",
        "minecraft:raw_iron", "minecraft:raw_iron_block", "minecraft:raw_copper", "minecraft:coal", "minecraft:andesite",
        "minecraft:diorite", "minecraft:granite", "minecraft:tuff", "minecraft:calcite");
    private static final Set<String> LIGHTS = Set.of("minecraft:torch","minecraft:wall_torch");
    private static final Set<String> HAZARDS = Set.of("minecraft:fire","minecraft:soul_fire","minecraft:cobweb",
        "minecraft:powder_snow","minecraft:pointed_dripstone");
    record Bounds(int minX,int minY,int minZ,int maxX,int maxY,int maxZ) {
        boolean contains(int x,int y,int z) {return x>=minX&&x<=maxX&&y>=minY&&y<=maxY&&z>=minZ&&z<=maxZ;}
        boolean column(int x,int z) {return x>=minX&&x<=maxX&&z>=minZ&&z<=maxZ;}
        boolean valid() {
            long dx=(long)maxX-minX+1,dy=(long)maxY-minY+1,dz=(long)maxZ-minZ+1;
            return dx>=1&&dx<=6&&dy>=2&&dy<=18&&dz>=1&&dz<=6&&dx*dy*dz<=648;
        }
    }
    record Cell(boolean loaded,String block,boolean air,boolean fluid,boolean blockEntity,
                boolean falling,boolean solid,boolean pending) {}
    interface World {Cell cell(int x,int y,int z);}
    record Inspection(int remaining,int available,int retainedLights,int pendingBlocks) {}
    enum Result { RUNNING, DONE, WAITING }
    private RockQuarryPolicy() {}

    static boolean requestAllowed(Bounds bounds,String item,String completion,int target) {
        return bounds.valid()&&ITEMS.contains(item)
            &&(completion.equals("collect")&&target>=1&&target<=648 || completion.equals("clear")&&target==0);
    }
    static boolean drops(String block,String item) {
        return switch(item) {
            case "minecraft:cobblestone" -> block.equals("minecraft:stone");
            case "minecraft:cobbled_deepslate" -> block.equals("minecraft:deepslate");
            case "minecraft:raw_iron" -> block.equals("minecraft:iron_ore")||block.equals("minecraft:deepslate_iron_ore");
            case "minecraft:raw_iron_block" -> block.equals("minecraft:raw_iron_block");
            case "minecraft:raw_copper" -> block.equals("minecraft:copper_ore")||block.equals("minecraft:deepslate_copper_ore");
            case "minecraft:coal" -> block.equals("minecraft:coal_ore")||block.equals("minecraft:deepslate_coal_ore");
            case "minecraft:andesite", "minecraft:diorite", "minecraft:granite", "minecraft:tuff", "minecraft:calcite" -> block.equals(item);
            default -> false;
        };
    }
    static Inspection inspect(World world,Bounds bounds,String item) {
        if(!bounds.valid())throw new IllegalArgumentException("Invalid bounded rock quarry");
        int remaining=0,available=0,retainedLights=0,pendingBlocks=0;
        for(int x=bounds.minX-BUFFER;x<=bounds.maxX+BUFFER;x++)
            for(int z=bounds.minZ-BUFFER;z<=bounds.maxZ+BUFFER;z++)
                for(int y=bounds.minY-2;y<=bounds.maxY+2;y++) {
                    Cell cell=world.cell(x,y,z);boolean inside=bounds.contains(x,y,z);
                    if(!cell.loaded||cell.fluid||cell.blockEntity||cell.falling
                            ||HAZARDS.contains(cell.block)
                            ||inside&&!cell.air&&!LIGHTS.contains(cell.block)&&!NATURAL.contains(cell.block)
                            ||inside&&cell.block.equals("minecraft:raw_iron_block")
                                &&(y<RAW_IRON_BLOCK_MIN_Y||y>RAW_IRON_BLOCK_MAX_Y))
                        throw new IllegalStateException("Rock quarry has a protected, wet, falling or unloaded cell at "+x+","+y+","+z);
                    if(bounds.column(x,z)&&y==bounds.minY-1&&!cell.solid)
                        throw new IllegalStateException("Rock quarry lacks solid bottom support at "+x+","+y+","+z);
                    if(inside&&cell.pending){remaining++;pendingBlocks++;}
                    else if(inside&&LIGHTS.contains(cell.block))retainedLights++;
                    else if(inside&&!cell.air){remaining++;if(drops(cell.block,item))available++;}
                }
        return new Inspection(remaining,available,retainedLights,pendingBlocks);
    }
    /** Start still requires Flight. Only the exact current native AREA may use its owned grounded state. */
    static boolean flightAllowed(boolean flightActive,boolean currentRockRequest,boolean currentMaterialScope,boolean exactOwnedArea) {
        return flightActive || currentRockRequest&&currentMaterialScope&&exactOwnedArea;
    }
    static boolean healthy(double health,int food,boolean underwater) {return health>=19&&food>=8&&!underwater;}
    static boolean toolAllowed(boolean diamondOrNetherite,int durability,int remaining,boolean silk,boolean collect) {
        return diamondOrNetherite&&durability>=remaining+32&&(!collect||!silk);
    }
    static Result result(String completion,int target,int before,int current,int remaining,boolean minerActive) {
        if(completion.equals("collect")&&target>0&&current-before>=target)return Result.DONE;
        if(completion.equals("clear")&&target==0&&remaining==0)return Result.DONE;
        return !minerActive?Result.WAITING:Result.RUNNING;
    }
    static boolean ownsCancel(String expected,String actual,String requestedWorld,String currentWorld,
                              long leaseRevision,long revision) {
        return expected!=null&&!expected.isBlank()&&expected.equals(actual)
            &&requestedWorld.equals(currentWorld)&&leaseRevision==revision;
    }
}
