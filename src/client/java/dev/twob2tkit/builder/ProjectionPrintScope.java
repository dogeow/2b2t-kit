package dev.twob2tkit.builder;

import dev.twob2tkit.automation.AutomationBridge;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Predicate;

/** The current work mask changes pacing and material demand, never full-model completion. */
public final class ProjectionPrintScope {
    private ProjectionPrintScope() {}
    static <T> List<T> select(Collection<T> positions,Predicate<T> allowed) {
        var selected=new ArrayList<T>();
        for(var position:positions)if(allowed.test(position))selected.add(position);
        return selected;
    }
    public static List<BlockPos> currentPositions(Minecraft client,Collection<BlockPos> positions) {
        return select(positions,position->AutomationBridge.projectionBatchAllows(client,position));
    }
}
