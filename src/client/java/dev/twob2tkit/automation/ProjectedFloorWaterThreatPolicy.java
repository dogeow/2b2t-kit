package dev.twob2tkit.automation;
import java.util.List;
/** A stationary bucket use above an observed intact floor; never a general enemy bypass. */
final class ProjectedFloorWaterThreatPolicy {
    record Threat(boolean current,boolean supported,boolean visible,double top){}
    static boolean permit(boolean geometry,boolean floor,boolean pose,boolean quiet,boolean projectileFree,
                          int floorY,List<Threat> threats){
        if(!geometry||!floor||!pose||!quiet||!projectileFree||threats==null)return false;
        for(var t:threats)if(t==null||!t.current||!t.supported||t.visible||!Double.isFinite(t.top)||t.top>floorY)return false;
        return true;
    }
}
