package dev.twob2tkit.automation;

import java.util.List;

/** Physical containment proof for a source-column placement, not a general hostile-ignore switch. */
final class SourceColumnThreatPolicy {
    record Workspace(boolean shellVerified,boolean horizontalContained,boolean atOrAboveFloor,
                     boolean verticallyEnclosed,boolean quiet,boolean projectileFree){}
    record Threat(boolean current,boolean supported,boolean ranged,boolean visible,
                  boolean belowFloor,double clearance){}
    private SourceColumnThreatPolicy(){}
    static boolean remoteCreeper(boolean enclosed,boolean current,boolean ordinary,boolean visible,
                                 boolean swelling,boolean belowFeet,double boxDistanceSquared){
        return enclosed&&current&&ordinary&&!visible&&!swelling&&belowFeet
            &&Double.isFinite(boxDistanceSquared)&&boxDistanceSquared>16*16;
    }
    static boolean shortRemoteCreeper(boolean fourRows,Workspace work,boolean current,boolean ordinary,
                                     boolean visible,boolean swelling,boolean belowFloor,
                                     double playerDistanceSquared,double structureDistanceSquared){
        return fourRows&&work!=null&&work.shellVerified&&work.horizontalContained&&work.atOrAboveFloor
            &&work.quiet&&work.projectileFree&&current&&ordinary&&!visible&&!swelling&&belowFloor
            &&Double.isFinite(playerDistanceSquared)&&Double.isFinite(structureDistanceSquared)
            &&playerDistanceSquared>8*8&&structureDistanceSquared>7*7;
    }
    static boolean permit(Workspace work,List<Threat> threats){
        if(work==null||!work.shellVerified||!work.horizontalContained||!work.atOrAboveFloor
                ||!work.quiet||!work.projectileFree||threats==null)return false;
        for(var threat:threats){
            if(threat==null||!threat.current||!threat.supported||threat.visible
                    ||!Double.isFinite(threat.clearance)||threat.clearance<0)return false;
            if(!work.verticallyEnclosed&&(!threat.belowFloor||threat.clearance<(threat.ranged?12:6)))return false;
        }
        return true;
    }
}
