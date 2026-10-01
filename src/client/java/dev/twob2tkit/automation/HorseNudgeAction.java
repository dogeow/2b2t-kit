package dev.twob2tkit.automation;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Minecraft-facing checks and the sole packet send for a horse nudge. */
final class HorseNudgeAction {
    private HorseNudgeAction() {}

    static int emptyHotbar(Minecraft c){
        int selected=c.player.getInventory().getSelectedSlot();
        if(c.player.getInventory().getItem(selected).isEmpty())return selected;
        for(int slot=0;slot<9;slot++)if(c.player.getInventory().getItem(slot).isEmpty())return slot;
        return -1;
    }

    static double emptyAttackDamage(Minecraft c,int emptySlot){
        int original=c.player.getInventory().getSelectedSlot();
        try{
            c.player.getInventory().setSelectedSlot(emptySlot);
            return c.player.getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE);
        }finally{c.player.getInventory().setSelectedSlot(original);}
    }

    static String escapeRejection(Minecraft c,Entity horse,Vec3 escape){
        Vec3 start=horse.position();double dx=escape.x-start.x,dz=escape.z-start.z;
        double travel=Math.hypot(dx,dz);if(!Double.isFinite(travel)||travel<1)return "Horse escape path is invalid";
        double ux=dx/travel,uz=dz/travel;AABB original=horse.getBoundingBox();
        AABB swept=original.expandTowards(ux*travel,0,uz*travel).inflate(.05);
        if(!c.level.getWorldBorder().isWithinBounds(swept))return "Horse escape path crosses the world border";
        if(!c.level.getEntitiesOfClass(Player.class,swept.inflate(8),
                player->player!=c.player&&player.isAlive()).isEmpty())
            return "Another player is near the horse escape path";
        for(double step=0;;step+=.5){
            double distance=Math.min(step,travel);AABB body=original.move(ux*distance,0,uz*distance);
            if(!loaded(c,body)||!c.level.noCollision(horse,body))return "Horse escape body path is occupied";
            int floorY=(int)Math.floor(body.minY-.05);
            for(int x=(int)Math.floor(body.minX+.01);x<=Math.floor(body.maxX-.01);x++)
                for(int z=(int)Math.floor(body.minZ+.01);z<=Math.floor(body.maxZ-.01);z++){
                    BlockPos floor=new BlockPos(x,floorY,z);var state=c.level.getBlockState(floor);
                    if(!c.level.hasChunkAt(floor)||!state.isCollisionShapeFullBlock(c.level,floor)
                            ||!state.getFluidState().isEmpty())return "Horse escape path lacks dry solid ground";
                }
            for(int x=(int)Math.floor(body.minX+.01);x<=Math.floor(body.maxX-.01);x++)
                for(int y=(int)Math.floor(body.minY+.01);y<=Math.floor(body.maxY-.01);y++)
                    for(int z=(int)Math.floor(body.minZ+.01);z<=Math.floor(body.maxZ-.01);z++){
                        BlockPos p=new BlockPos(x,y,z);var state=c.level.getBlockState(p);
                        if(!state.getFluidState().isEmpty()||state.is(Blocks.FIRE)||state.is(Blocks.SOUL_FIRE)
                                ||state.is(Blocks.COBWEB)||state.is(Blocks.POWDER_SNOW))
                            return "Horse escape path contains a fluid or movement hazard";
                    }
            if(distance>=travel)break;
        }
        return null;
    }

    /** Exactly one call site sends an attack packet; the selected slot is restored in all outcomes. */
    static void attackOnce(Minecraft c,Entity horse,int emptySlot){
        int original=c.player.getInventory().getSelectedSlot();
        if(emptySlot<0||emptySlot>=9||!c.player.getInventory().getItem(emptySlot).isEmpty())
            throw new IllegalStateException("A verified empty hotbar slot is required");
        c.options.keyAttack.setDown(false);c.options.keySprint.setDown(false);c.player.setSprinting(false);
        try{
            c.player.getInventory().setSelectedSlot(emptySlot);
            c.gameMode.attack(c.player,horse);
            c.player.swing(InteractionHand.MAIN_HAND);
        }finally{
            c.player.getInventory().setSelectedSlot(original);
            ((dev.twob2tkit.mixin.MultiPlayerGameModeAccessor)c.gameMode).twob2tkit$syncSelectedSlot();
        }
    }

    private static boolean loaded(Minecraft c,AABB box){
        for(int x=(int)Math.floor(box.minX);x<=Math.floor(box.maxX-1e-6);x++)
            for(int z=(int)Math.floor(box.minZ);z<=Math.floor(box.maxZ-1e-6);z++)
                if(!c.level.hasChunkAt(new BlockPos(x,(int)Math.floor(box.minY),z)))return false;
        return true;
    }
}
