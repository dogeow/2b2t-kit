package dev.twob2tkit.runtime.api;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import java.util.*;
/** Stable host boundary: observation/collision and all real interactions stay in the host. */
public interface BuildNavigation {
    interface World { boolean clear(BlockPos p); boolean edge(BlockPos from,BlockPos to); }
    record Result(List<BlockPos> nodes,int expanded) {}
    interface Search { Result advance(int maxNodes,long deadlineNanos); int expanded(); }
    record Motion(boolean arrived,boolean vertical,double speed,Vec3 probe) {
        public Motion {
            if(!Double.isFinite(speed)||speed<0||speed>.035||probe==null||!Double.isFinite(probe.lengthSqr())||probe.length()>.36
                ||arrived&&(speed!=0||probe.lengthSqr()!=0))throw new IllegalArgumentException("Unsafe movement proposal");
        }
    }
    record Policy(int sliceNodes,long sliceNanos,int totalNodes,int quietTicks,int retryTicks,int stallTicks) {
        public Policy {
            if(sliceNodes<1||sliceNodes>512||sliceNanos<1||sliceNanos>8_000_000L||totalNodes<sliceNodes||totalNodes>100000
                ||quietTicks<2||retryTicks<quietTicks||retryTicks>400||stallTicks<10||stallTicks>200)throw new IllegalArgumentException("Unsafe build policy");
        }
    }
    String version();
    Policy policy();
    Search search(World world,BlockPos start,Collection<BlockPos> goals);
    List<BlockPos> stations(BlockPos target);
    Motion motion(Vec3 delta);
}
