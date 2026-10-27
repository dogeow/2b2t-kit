package dev.twob2tkit.runtime.engine;
final class ChannelWaterPlacementPolicy {
 static boolean shape(int length,int width,int row){return length>=2&&length<=8&&width==2&&row>=0&&row<2;}
 static boolean geometry(int length,int width,int floors,int hoppers,int sides,int outlets){return shape(length,width,0)&&floors==(length-1)*2&&hoppers==2&&sides==length*2+2&&outlets==2;}
}
