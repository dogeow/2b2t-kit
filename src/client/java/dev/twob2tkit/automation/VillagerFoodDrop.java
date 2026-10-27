package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.item.Items;

/** One ordinary Q input toward a current adult; pickup and breeding need later evidence. */
final class VillagerFoodDrop {
    static void require(boolean owned,boolean manual,boolean healthy,boolean exactAdult,boolean visible,
                        boolean emptyInventoryMenu,boolean bread,int count,int expected,double distance){
        if(!owned||manual||!healthy||!exactAdult||!visible||!emptyInventoryMenu||!bread||count<1||count!=expected
                ||!Double.isFinite(distance)||distance>3)
            throw new IllegalStateException("One bread drop needs the same healthy adult within three blocks and the exact held bread stack");
    }
    static Villager target(Minecraft c,JsonObject r,boolean owned,boolean manual){
        var entity=c.level.getEntity(r.get("entity_id").getAsInt());
        if(!(entity instanceof Villager villager))throw new IllegalStateException("Current adult villager required for bread");
        var stack=c.player.getMainHandItem();
        require(owned,manual,c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=18&&!c.player.isInWater()
                &&!c.player.isOnFire()&&!c.player.isUsingItem()&&c.player.hurtTime==0,
            villager.getUUID().toString().equals(r.get("expected_uuid").getAsString())&&villager.isAlive()&&!villager.isRemoved()
                &&!villager.isBaby()&&!villager.hasCustomName()&&!villager.isPassenger()&&villager.getHealth()>=19,
            c.player.hasLineOfSight(villager),c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty(),
            stack.is(Items.BREAD),stack.getCount(),r.get("expected_count").getAsInt(),c.player.distanceTo(villager));
        return villager;
    }
    static void drop(Minecraft c,JsonObject r,boolean owned,boolean manual){
        var villager=target(c,r,owned,manual);
        var delta=villager.position().add(0,villager.getBbHeight()*.55,0).subtract(c.player.getEyePosition());
        if(delta.lengthSqr()<.01||c.player.getViewVector(1).dot(delta.normalize())<.95)
            throw new IllegalStateException("Villager moved outside the original bread throw direction");
        if(!c.player.drop(false))throw new IllegalStateException("Normal bread drop did not dispatch; observe inventory before another intent");
    }
}
