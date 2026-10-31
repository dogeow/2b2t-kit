package dev.twob2tkit.automation;

import java.util.List;

/** A sealed3x1x9 legacy or explicit3x1x4 source chamber; never the separate overflow channel above it. */
final class ProjectedSourceColumnPolicy {
    record Bounds(int minX,int minY,int minZ,int maxX,int maxY,int maxZ) {
        boolean valid(){return validRows(9);}
        boolean validRows(int rows){return (rows==4||rows==9)&&(long)maxX-minX==2&&(long)maxY-minY==rows-1&&minZ==maxZ
            &&minY>Integer.MIN_VALUE&&maxY<Integer.MAX_VALUE
            &&minX>-30000000&&maxX<30000000&&minZ>-30000000&&minZ<30000000;}
        boolean contains(int x,int y,int z){return containsRows(x,y,z,9);}
        boolean containsRows(int x,int y,int z,int rows){return validRows(rows)&&x>=minX&&x<=maxX&&y>=minY&&y<=maxY&&z==minZ;}

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
        return rejection(cells,target,before,verifiedFloors,verifiedWalls,dryTop,actorReady,otherLiving,9);
    }
    static String rejection(List<Cell> cells,int target,boolean before,int verifiedFloors,int verifiedWalls,
                            boolean dryTop,boolean actorReady,boolean otherLiving,int rows){
        int count=rows*3;
        if((rows!=4&&rows!=9)||cells==null||cells.size()!=count||target<0||target>=count)return "Exact profiled source chamber required";
        if(verifiedFloors!=3||verifiedWalls!=rows*8)return "Source chamber floor or perimeter is not sealed";
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
