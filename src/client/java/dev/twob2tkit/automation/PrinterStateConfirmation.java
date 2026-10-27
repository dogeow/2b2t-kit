package dev.twob2tkit.automation;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import java.util.*;

/** Intrinsic placement confirmation; final projection audits still compare every property. */
public final class PrinterStateConfirmation {
    private PrinterStateConfirmation(){}
    public static boolean matches(BlockState expected,BlockState actual){
        if(expected.getBlock()!=actual.getBlock())return false;
        boolean connections=expected.getBlock() instanceof FenceBlock||expected.getBlock() instanceof WallBlock||expected.getBlock() instanceof IronBarsBlock;
        boolean persistentLeaves=expected.getBlock() instanceof LeavesBlock
            && expected.getValue(LeavesBlock.PERSISTENT)&&actual.getValue(LeavesBlock.PERSISTENT);
        for(var property:expected.getProperties()){
            String name=property.getName();
            if(connections&&Set.of("north","south","east","west","up").contains(name))continue;
            // Wire shape follows the currently built neighbors. Completing a row
            // can change these connections after its individual placement ACK.
            if(expected.getBlock() instanceof RedStoneWireBlock&&Set.of("north","south","east","west").contains(name))continue;
            // Leaf distance is recomputed from neighboring logs after placement;
            // it can legitimately change as the rest of the projection is built.
            if(persistentLeaves&&name.equals("distance"))continue;
            if(expected.getBlock() instanceof StairBlock&&name.equals("shape"))continue;
            if(!actual.hasProperty(property)||!Objects.equals(expected.getValue(property),actual.getValue(property)))return false;
        }
        return true;
    }
    public static BlockState placementExpectation(BlockState goal,BlockState predicted){
        if(predicted==null||matches(goal,predicted))return goal;
        // A double slab takes two normal uses. Only the predicted first half
        // is an intermediate ACK; matches(goal, actual) remains exact.
        if(goal.getBlock() instanceof SlabBlock&&goal.getBlock()==predicted.getBlock()
                &&goal.getValue(SlabBlock.TYPE)==net.minecraft.world.level.block.state.properties.SlabType.DOUBLE
                &&predicted.getValue(SlabBlock.TYPE)!=net.minecraft.world.level.block.state.properties.SlabType.DOUBLE){
            boolean sameOtherProperties=true;
            for(var property:goal.getProperties())if(property!=SlabBlock.TYPE
                    &&(!predicted.hasProperty(property)||!Objects.equals(goal.getValue(property),predicted.getValue(property))))sameOtherProperties=false;
            if(sameOtherProperties)return predicted;
        }
        if(goal.getBlock() instanceof FlowerPotBlock&&!goal.is(Blocks.FLOWER_POT)&&predicted.is(Blocks.FLOWER_POT))return predicted;
        String wanted=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(goal.getBlock()).toString();
        String placed=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(predicted.getBlock()).toString();
        boolean stripping=placed.startsWith("minecraft:")&&wanted.equals("minecraft:stripped_"+placed.substring("minecraft:".length()));
        if(goal.getBlock()!=predicted.getBlock()&&!stripping)return goal;
        for(var property:goal.getProperties()){
            String name=property.getName();
            if(name.equals("open")&&(goal.getBlock() instanceof DoorBlock||goal.getBlock() instanceof TrapDoorBlock||goal.getBlock() instanceof FenceGateBlock))continue;
            if(name.equals("lit")&&(goal.getBlock() instanceof CampfireBlock||goal.getBlock() instanceof CandleBlock||passiveTorchTransition(goal,predicted)))continue;
            if(!predicted.hasProperty(property)||!Objects.equals(goal.getValue(property),predicted.getValue(property)))return goal;
        }
        return predicted;
    }
    /** A powered support turns a newly placed lit torch off after its normal scheduled tick. */
    public static boolean passiveTorchTransition(BlockState goal,BlockState initial){
        if(goal==null||initial==null||goal.getBlock()!=initial.getBlock()
                ||!(goal.getBlock() instanceof RedstoneTorchBlock||goal.getBlock() instanceof RedstoneWallTorchBlock)
                ||goal.getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.LIT)
                ||!initial.getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.LIT))return false;
        for(var property:goal.getProperties())if(!property.getName().equals("lit")
                &&(!initial.hasProperty(property)||!Objects.equals(goal.getValue(property),initial.getValue(property))))return false;
        return true;
    }
}
