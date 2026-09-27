package dev.twob2tkit.automation;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import java.util.List;

/** One short-lived, observed route to actual air, owned by a material job. */
final class MaterialAirRoute {
    private String world="",job="",gear="",sampleWorld="",sampleGear="";
    private double anchorX,anchorZ,lastClearX,lastClearZ,returnY,sampleX,sampleZ;
    private long expires;
    private final MaterialAirCalibration calibration=new MaterialAirCalibration();
    private String sampleRequest="";
    private int startAir,minAir;
    private double startY,lastSubmergedY;
    private long startMillis,lastSubmergedMillis;

    void clearRoute(){world="";job="";expires=0;sampleRequest="";calibration.clearDive();}

    void configure(Minecraft c,String currentWorld,String currentJob,String helmet,
                   Vec3 target,long now){
        if(c.player==null||c.level==null||!c.player.isUnderWater()
                ||c.player.getHealth()<19||currentWorld.isBlank()||currentJob.isBlank()
                ||!Double.isFinite(target.x)||!Double.isFinite(target.y)||!Double.isFinite(target.z)
                ||target.y<c.level.getSeaLevel()+1||target.y>c.level.getSeaLevel()+4
                ||Math.hypot(target.x-c.player.getX(),target.z-c.player.getZ())>.75)
            throw new IllegalStateException("Material air return requires a healthy submerged player and nearby open air");
        if(!sampleWorld.equals(currentWorld)||!sampleGear.equals(helmet)
                ||Math.hypot(sampleX-c.player.getX(),sampleZ-c.player.getZ())>64){
            calibration.clearHistory();sampleWorld=currentWorld;sampleGear=helmet;
            sampleX=c.player.getX();sampleZ=c.player.getZ();
        }
        if(!clearColumn(c,c.player.getX(),c.player.getZ(),target.y))
            throw new IllegalStateException("Verified vertical return to breathable air is absent");
        world=currentWorld;job=currentJob;gear=helmet;anchorX=c.player.getX();anchorZ=c.player.getZ();
        lastClearX=anchorX;lastClearZ=anchorZ;returnY=target.y;expires=now+60000;
        calibration.enterDive(world,job,gear,now,c.player.getMaxAirSupply(),
            Math.max(0,returnY-c.player.getY()));
    }

    boolean owned(String currentWorld,String currentJob,String helmet,Minecraft c){
        return c.player!=null&&c.level!=null&&world.equals(currentWorld)
            &&job.equals(currentJob)&&gear.equals(helmet)
            &&Math.abs(c.player.getX()-anchorX)<=3&&Math.abs(c.player.getZ()-anchorZ)<=3;
    }

    boolean configuredJob(String currentWorld,String currentJob){
        return !world.isBlank()&&world.equals(currentWorld)&&job.equals(currentJob);
    }

    boolean fresh(String currentWorld,String currentJob,String helmet,Minecraft c,long now){
        return owned(currentWorld,currentJob,helmet,c)&&now<=expires;
    }

    double returnY(){return returnY;}
    long expires(){return expires;}
    long budgetValidUntil(String currentWorld,String currentJob,String helmet){
        return calibration.isPinned(currentWorld,currentJob,helmet)
            ?Math.min(expires,calibration.pinnedUntil()):expires;
    }
    boolean returnDue(String currentWorld,String currentJob,String helmet,long now){
        return calibration.isPinned(currentWorld,currentJob,helmet)
            &&(now>=expires||calibration.returnDue(currentWorld,currentJob,helmet,now));
    }
    void observeExposure(Minecraft c,String currentWorld,String currentJob,String helmet){
        if(c.player==null||!c.player.isUnderWater()
                ||!owned(currentWorld,currentJob,helmet,c))calibration.clearDive();
    }

    MaterialAirBudget.Estimate estimate(Minecraft c,String currentWorld,String currentJob,
                                        String helmet,long now){
        if(c.player==null)return MaterialAirBudget.estimate(300,Double.NaN,List.of());
        observeExposure(c,currentWorld,currentJob,helmet);
        boolean pinned=calibration.isPinned(currentWorld,currentJob,helmet);
        if((!fresh(currentWorld,currentJob,helmet,c,now)&&!pinned)
                ||!clearColumn(c,c.player.getX(),c.player.getZ(),returnY)
                ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER))
            return MaterialAirBudget.estimate(c.player.getMaxAirSupply(),Double.NaN,List.of());
        lastClearX=c.player.getX();lastClearZ=c.player.getZ();
        double climb=Math.max(0,returnY-c.player.getY());
        var result=MaterialAirBudget.estimate(c.player.getMaxAirSupply(),climb,
            calibration.samples(currentWorld,currentJob,helmet,c.player.isUnderWater(),now));
        return result.source().equals("fallback")
            ?EquipmentAirBudget.estimate(c.player.getMaxAirSupply(),climb,
                c.player.getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.OXYGEN_BONUS))
            :result;
    }

    Vec3 emergencyTarget(Minecraft c,String currentWorld,String currentJob,String helmet){
        if(!owned(currentWorld,currentJob,helmet,c))return null;
        if(clearColumn(c,c.player.getX(),c.player.getZ(),returnY)){
            lastClearX=c.player.getX();lastClearZ=c.player.getZ();
            return new Vec3(lastClearX,returnY,lastClearZ);
        }
        // The existing flight controller rises before moving horizontally.
        // A previously clear neighbor is not a proven escape from this column.
        return null;
    }

    void beginAscent(Minecraft c,String requestId,double targetY){
        sampleRequest="";
        if(c.player==null||!c.player.isUnderWater()||targetY<returnY)return;
        sampleRequest=requestId;startAir=c.player.getAirSupply();minAir=startAir;
        startY=c.player.getY();lastSubmergedY=startY;
        startMillis=System.currentTimeMillis();lastSubmergedMillis=startMillis;
    }

    void observeAscent(Minecraft c,String requestId){
        if(c.player==null||!sampleRequest.equals(requestId)||!c.player.isUnderWater())return;
        minAir=Math.min(minAir,c.player.getAirSupply());
        lastSubmergedY=c.player.getY();lastSubmergedMillis=System.currentTimeMillis();
    }

    void finishAscent(Minecraft c,String requestId,boolean done){
        if(sampleRequest.isEmpty()||!sampleRequest.equals(requestId))return;
        sampleRequest="";
        if(!done||c.player==null||c.player.isUnderWater()||c.player.getHealth()<19
                ||c.player.getY()<returnY-1||startAir-minAir<1)return;
        double rise=Math.max(0,lastSubmergedY-startY);
        long elapsed=lastSubmergedMillis-startMillis;
        if(rise<2||elapsed<200)return;
        calibration.add(new MaterialAirBudget.Sample(rise,startAir-minAir,elapsed),
            System.currentTimeMillis());
    }

    static boolean clearColumn(Minecraft c,double x,double z,double top){
        if(c.player==null||c.level==null||!Double.isFinite(x)||!Double.isFinite(z)
                ||!Double.isFinite(top)||top<c.player.getY()+1||top-c.player.getY()>64)return false;
        BlockPos feet=BlockPos.containing(x,top,z),head=BlockPos.containing(x,top+1.6,z);
        if(!c.level.hasChunkAt(feet)||!c.level.hasChunkAt(head)
                ||!c.level.getFluidState(feet).isEmpty()
                ||!c.level.getFluidState(head).isEmpty())return false;
        for(double offset=.25;offset<=top-c.player.getY()+.25;offset+=.25){
            double dy=Math.min(offset,top-c.player.getY());
            var box=c.player.getBoundingBox().move(x-c.player.getX(),dy,z-c.player.getZ());
            if(!c.level.noCollision(c.player,box)||lavaIn(c,box))return false;
        }
        return true;
    }

    private static boolean lavaIn(Minecraft c,net.minecraft.world.phys.AABB body){
        for(int x=(int)Math.floor(body.minX);x<=Math.floor(body.maxX-1e-6);x++)
            for(int y=(int)Math.floor(body.minY);y<=Math.floor(body.maxY-1e-6);y++)
                for(int z=(int)Math.floor(body.minZ);z<=Math.floor(body.maxZ-1e-6);z++){
                    BlockPos p=new BlockPos(x,y,z);
                    if(!c.level.hasChunkAt(p)
                            ||c.level.getFluidState(p).is(net.minecraft.world.level.material.Fluids.LAVA))return true;
                }
        return false;
    }
}
