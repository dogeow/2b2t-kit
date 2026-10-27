package dev.twob2tkit.combat;

import net.minecraft.world.phys.Vec3;

/** Actual repeated environmental losses at one position, independent of task/food state. */
final class EnvironmentalDamageWindow {
    private Object world,player,connection;
    private long observedAt=-1,firstLossAt=-1,lastLossAt=-1;
    private float previousHealth=Float.NaN;
    private Vec3 anchor;
    private int losses;
    private boolean triggered;

    void reset(){
        world=player=connection=null;observedAt=-1;previousHealth=Float.NaN;
        triggered=false;clearLosses();
    }
    private void clearLosses(){firstLossAt=lastLossAt=-1;anchor=null;losses=0;}
    boolean observe(Object currentWorld,Object currentPlayer,Object currentConnection,long now,
                    float health,Vec3 position,boolean automated,boolean environmentalSource){
        if(!automated||currentWorld==null||currentPlayer==null||currentConnection==null||now<0
                ||!Float.isFinite(health)||health<=0||position==null
                ||!Double.isFinite(position.x)||!Double.isFinite(position.y)||!Double.isFinite(position.z)){
            reset();return false;
        }
        if(world!=currentWorld||player!=currentPlayer||connection!=currentConnection||now<observedAt){
            reset();world=currentWorld;player=currentPlayer;connection=currentConnection;
        }
        if(triggered||now==observedAt)return false;
        if(anchor!=null&&(position.distanceToSqr(anchor)>.75*.75||now-lastLossAt>3500))clearLosses();
        boolean loss=Float.isFinite(previousHealth)&&health<previousHealth-.05f;
        previousHealth=health;observedAt=now;
        if(!loss)return false; // Partial regeneration cannot erase a still-active burn window.
        if(!environmentalSource){clearLosses();return false;}
        if(anchor==null){anchor=position;firstLossAt=lastLossAt=now;losses=1;return false;}
        // Packet/tick duplicate observations are not separate injuries.
        if(now-lastLossAt<500)return false;
        lastLossAt=now;losses++;
        if(losses>=2&&now-firstLossAt>=500){triggered=true;return true;}
        return false;
    }
}
