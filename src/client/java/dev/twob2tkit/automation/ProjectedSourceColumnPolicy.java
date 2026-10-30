package dev.twob2tkit.automation;

import java.util.List;

/** One sealed 3x1x9 source chamber; never the separate overflow channel above it. */
final class ProjectedSourceColumnPolicy {
    record Bounds(int minX,int minY,int minZ,int maxX,int maxY,int maxZ) {
        boolean valid(){return (long)maxX-minX==2&&(long)maxY-minY==8&&minZ==maxZ
            &&minY>Integer.MIN_VALUE&&maxY<Integer.MAX_VALUE
            &&minX>-30000000&&maxX<30000000&&minZ>-30000000&&minZ<30000000;}
        boolean contains(int x,int y,int z){return valid()&&x>=minX&&x<=maxX&&y>=minY&&y<=maxY&&z==minZ;}
    }
    record Cell(int goalLevel,int actualLevel,boolean originalSource){}
    private ProjectedSourceColumnPolicy(){}
    static boolean exclusivePlace(boolean place,boolean column,boolean drain,boolean channel){return place&&!column&&!drain&&!channel;}
    static boolean actorReady(double health,int food,int air,int maximum,boolean lava,boolean alive){
        return alive&&!lava&&Double.isFinite(health)&&health>=19&&food>=16&&maximum>0
            &&air>=Math.min(270,maximum);
    }
    static boolean samePinned(String actual,String pinned,boolean floor){
        if(actual==null||pinned==null)return false;
        if(actual.equals(pinned))return true;
        String prefix="Block{minecraft:dropper}[facing=up,";
        return floor&&actual.startsWith(prefix)&&pinned.startsWith(prefix)
            &&actual.replace("triggered=true","triggered=false").equals(pinned.replace("triggered=true","triggered=false"));
    }
    static String rejection(List<Cell> cells,int target,boolean before,int verifiedFloors,int verifiedWalls,
                            boolean dryTop,boolean actorReady,boolean otherLiving){
        if(cells==null||cells.size()!=27||target<0||target>=27)return "Exact 27-cell source chamber required";
        if(verifiedFloors!=3||verifiedWalls!=72)return "Source chamber floor or perimeter is not sealed";
        if(!dryTop)return "Overflow above the chamber must remain dry during source repair";
        if(!actorReady||otherLiving)return "Source service needs healthy oxygen reserve and no other living entity";
        for(var cell:cells){
            if(cell==null||cell.goalLevel!=0||cell.actualLevel< -1||cell.actualLevel>15)
                return "Every chamber cell must be projected source water and actual air or plain water";
            if(cell.originalSource&&cell.actualLevel!=0)return "A previously observed source changed";
        }
        int state=cells.get(target).actualLevel;
        if(before?state==0:state!=0)return "Target source already present or not confirmed after use";
        return null;
    }
}
