package dev.twob2tkit.runtime.engine;

/** Conservative physical enclosure proof; no entity death or combat completion credit. */
final class EnclosedHostileGeometry {
    record Box(double minX,double minY,double minZ,double maxX,double maxY,double maxZ) {
        boolean valid(){return Double.isFinite(minX)&&Double.isFinite(minY)&&Double.isFinite(minZ)
            &&Double.isFinite(maxX)&&Double.isFinite(maxY)&&Double.isFinite(maxZ)
            &&minX<maxX&&minY<maxY&&minZ<maxZ;}
        boolean overlapsXZ(int x,int z,int width,int depth){return maxX>x&&minX<x+width&&maxZ>z&&minZ<z+depth;}
    }
    interface World {
        boolean wall(int x,int y,int z);
        boolean floor(int x,int z,double feet);
        boolean clear(int x,int z,int width,int depth,double feet,double top);
    }
    static boolean ordinaryMovement(double jump,double step,double gravity){
        return Double.isFinite(jump)&&Double.isFinite(step)&&Double.isFinite(gravity)
            &&jump>=0&&jump<=.420001&&step>=0&&step<=.600001&&gravity>=.079999;
    }
    static boolean sealed(World world,Box mob,Box player){
        if(!mob.valid()||!player.valid()||mob.maxY-mob.minY<=.1)return false;
        int topCourse=(int)Math.ceil(mob.minY-1e-6)+2;
        int cx=(int)Math.floor((mob.minX+mob.maxX)/2),cz=(int)Math.floor((mob.minZ+mob.maxZ)/2);
        for(int width=1;width<=3;width++)for(int depth=1;depth<=3;depth++)
            for(int x=cx-width+1;x<=cx;x++)for(int z=cz-depth+1;z<=cz;z++){
                if(mob.minX<x-1e-6||mob.maxX>x+width+1e-6||mob.minZ<z-1e-6||mob.maxZ>z+depth+1e-6
                    ||player.overlapsXZ(x,z,width,depth))continue;
                // Falling ground mobs remain contained only if the entire shaft is sealed to its real floor.
                for(double feet=Math.floor((mob.minY+1e-6)*2)/2;feet>=mob.minY-24;feet-=.5){
                    int course=(int)Math.ceil(feet-1e-6);
                    if(mob.maxY-mob.minY<=course-feet+1e-6)continue;
                    boolean ok=true;
                    for(int dx=0;dx<width;dx++)for(int dz=0;dz<depth;dz++)ok&=world.floor(x+dx,z+dz,feet);
                    if(!ok)continue;
                    for(int y=course;y<topCourse;y++){
                        for(int dx=0;dx<width;dx++)ok&=world.wall(x+dx,y,z-1)&&world.wall(x+dx,y,z+depth);
                        for(int dz=0;dz<depth;dz++)ok&=world.wall(x-1,y,z+dz)&&world.wall(x+width,y,z+dz);
                    }
                    if(ok&&world.clear(x,z,width,depth,feet,topCourse+mob.maxY-mob.minY))return true;
                }
            }
        return false;
    }
}
