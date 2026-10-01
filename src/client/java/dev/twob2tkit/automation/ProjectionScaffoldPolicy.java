package dev.twob2tkit.automation;

import java.util.Objects;

/** Pure admission rules for one exact horizontal row, not general scaffolding. */
final class ProjectionScaffoldPolicy {
    static final int MAX_ROW_LENGTH=128, MAX_REQUEST_TARGETS=512, SETTLE_TICKS=8;
    static final double MAX_HORIZONTAL_SPEED=.22, MAX_VERTICAL_SPEED=.12;
    private static final double BODY_HALF_WIDTH=.31, LANE_MARGIN=.18;
    record Row(int minX,int maxX,int y,int z,String item) {}
    record Point(int x,int y,int z) {}
    private ProjectionScaffoldPolicy() {}

    static boolean rowValid(Row row,int targetCount,boolean plainCube) {
        if(row==null||!plainCube||row.item()==null||!row.item().matches("minecraft:[a-z0-9_./-]+"))return false;
        long length=(long)row.maxX()-row.minX()+1;
        return length>=1&&length<=MAX_ROW_LENGTH&&targetCount==length
            &&targetCount<=MAX_REQUEST_TARGETS&&row.y()>=-64&&row.y()<=319;
    }
    static boolean contains(Row row,int x,int y,int z) {
        return row!=null&&x>=row.minX()&&x<=row.maxX()&&y==row.y()&&z==row.z();
    }
    static boolean scopeAllowed(String expectedWorld,String currentWorld,long expectedRevision,long revision,
                                String expectedProjection,String currentProjection) {
        return expectedWorld!=null&&!expectedWorld.isBlank()&&expectedWorld.equals(currentWorld)
            &&expectedRevision>=0&&expectedRevision==revision
            &&expectedProjection!=null&&!expectedProjection.isBlank()&&expectedProjection.equals(currentProjection);
    }
    static boolean safe(boolean connected,double health,int food,boolean manual,boolean guardArmed,
                        boolean pveOnly,boolean busy,boolean hold,boolean damaged) {
        return connected&&Double.isFinite(health)&&health>=19&&food>=8&&food<=20
            &&!manual&&guardArmed&&pveOnly&&!busy&&!hold&&!damaged;
    }
    static Point predictedFootTarget(double x,double feetY,double z,double vx,double vy,double vz) {
        return predictedFootTarget(x,feetY,z,vx,vy,vz,false,false);
    }
    /** Actual Meteor 26.1.2-42 air-place prediction, Shift branch, and body-layer clamp. */
    static Point predictedFootTarget(double x,double feetY,double z,double vx,double vy,double vz,
                                     boolean shift,boolean jump) {
        if(!finite(x,feetY,z,vx,vy,vz))return null;
        double rawY=feetY+vy-.75;
        Integer px=floor(x+vx),py=floor(rawY),pz=floor(z+vz),bodyY=floor(feetY);
        if(px==null||py==null||pz==null||bodyY==null)return null;
        long targetY=py;
        if(shift&&!jump&&feetY+rawY>-1)targetY--;
        if(targetY>=bodyY)targetY=(long)bodyY-1;
        if(targetY<Integer.MIN_VALUE||targetY>Integer.MAX_VALUE)return null;
        return new Point(px,(int)targetY,pz);
    }
    static boolean motionAllowed(Row row,double x,double feetY,double z,double vx,double vy,double vz,
                                 boolean shift) {
        return motionAllowed(row,x,feetY,z,vx,vy,vz,shift,false);
    }
    static boolean motionAllowed(Row row,double x,double feetY,double z,double vx,double vy,double vz,
                                 boolean shift,boolean jump) {
        if(row==null||shift||jump||!finite(x,feetY,z,vx,vy,vz)
                ||Math.hypot(vx,vz)>MAX_HORIZONTAL_SPEED+1e-9||Math.abs(vy)>MAX_VERTICAL_SPEED+1e-9)return false;
        Integer nowY=floor(feetY),nextY=floor(feetY+vy);
        if(nowY==null||nextY==null||nowY!=row.y()+1||nextY!=row.y()+1)return false;
        if(!footprint(row,x,z)||!footprint(row,x+vx,z+vz))return false;
        var target=predictedFootTarget(x,feetY,z,vx,vy,vz);
        return target!=null&&contains(row,target.x(),target.y(),target.z());
    }
    static boolean candidateAllowed(Row row,Point actualTarget,Point predicted,boolean loaded,
                                    boolean replaceable,boolean fluid,boolean collisionFree,
                                    boolean plainCube,String expectedItem) {
        return row!=null&&actualTarget!=null&&Objects.equals(actualTarget,predicted)
            &&contains(row,actualTarget.x(),actualTarget.y(),actualTarget.z())
            &&loaded&&replaceable&&!fluid&&collisionFree&&plainCube&&row.item().equals(expectedItem);
    }
    static boolean confirmed(boolean serverConfirmed,boolean currentStateMatches,int inventoryBefore,
                             int inventoryNow,long ackTick,long tick) {
        return serverConfirmed&&currentStateMatches&&inventoryBefore>0&&inventoryNow>=0
            &&inventoryBefore-inventoryNow==1&&ackTick>=0&&tick>=ackTick&&tick-ackTick>=SETTLE_TICKS;
    }
    static boolean cumulativeInventoryMatches(int baseline,int inventoryNow,int sent) {
        return baseline>=0&&inventoryNow>=0&&sent>=0&&sent<=baseline&&baseline-inventoryNow==sent;
    }
    static boolean windowAvailable(int pending){return pending>=0&&pending<2;}
    /** One in-flight block, one acknowledgement, and one counted inventory delta. */
    static final class AckTracker {
        private Point target;
        private int before;
        private long sentTick,ackTick=-1;
        boolean begin(Point next,int inventoryBefore,long tick) {
            if(target!=null||next==null||inventoryBefore<1||tick<0)return false;
            target=next;before=inventoryBefore;sentTick=tick;ackTick=-1;return true;
        }
        boolean acknowledge(Point actual,long tick) {
            if(target==null||!target.equals(actual)||tick<sentTick||ackTick>=0)return false;
            ackTick=tick;return true;
        }
        boolean take(Point actual,boolean currentStateMatches,int inventoryNow,long tick) {
            if(target==null||!target.equals(actual)||!confirmed(ackTick>=0,currentStateMatches,before,inventoryNow,ackTick,tick))return false;
            target=null;ackTick=-1;return true;
        }
        boolean pending(){return target!=null;}
        Point target(){return target;}
    }
    private static boolean footprint(Row row,double x,double z) {
        return x>=row.minX()+BODY_HALF_WIDTH&&x<=row.maxX()+1-BODY_HALF_WIDTH
            &&Math.abs(z-(row.z()+.5))<=LANE_MARGIN+1e-9;
    }
    private static boolean finite(double... values){for(double value:values)if(!Double.isFinite(value))return false;return true;}
    private static Integer floor(double value){
        double result=Math.floor(value);
        return Double.isFinite(result)&&result>=Integer.MIN_VALUE&&result<=Integer.MAX_VALUE?(int)result:null;
    }
}
