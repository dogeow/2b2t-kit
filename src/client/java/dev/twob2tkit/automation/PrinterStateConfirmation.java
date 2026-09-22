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
        for(var property:expected.getProperties()){
            String name=property.getName();
            if(connections&&Set.of("north","south","east","west","up").contains(name))continue;
            if(expected.getBlock() instanceof StairBlock&&name.equals("shape"))continue;
            if(!actual.hasProperty(property)||!Objects.equals(expected.getValue(property),actual.getValue(property)))return false;
        }
        return true;
    }
    public static BlockState placementExpectation(BlockState goal,BlockState predicted){
        if(predicted==null||matches(goal,predicted))return goal;
        String wanted=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(goal.getBlock()).toString();
        String placed=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(predicted.getBlock()).toString();
        boolean stripping=placed.startsWith("minecraft:")&&wanted.equals("minecraft:stripped_"+placed.substring("minecraft:".length()));
        if(goal.getBlock()!=predicted.getBlock()&&!stripping)return goal;
        for(var property:goal.getProperties()){
            String name=property.getName();
            if(name.equals("open")&&(goal.getBlock() instanceof DoorBlock||goal.getBlock() instanceof TrapDoorBlock||goal.getBlock() instanceof FenceGateBlock))continue;
            if(name.equals("lit")&&(goal.getBlock() instanceof CampfireBlock||goal.getBlock() instanceof CandleBlock))continue;
            if(!predicted.hasProperty(property)||!Objects.equals(goal.getValue(property),predicted.getValue(property)))return goal;
        }
        return predicted;
    }
}
