package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.entity.vehicle.boat.AbstractBoat;
import net.minecraft.tags.ItemTags;
import java.util.HashSet;
import java.util.Set;

/** One normal attack on an exact boat after checking a dry disembarkation area. */
final class BoatRecovery {
    static boolean foodPassenger(String type,boolean allowed,boolean baby,boolean named,float health,float maximum){
        return allowed&&!baby&&!named&&Set.of("minecraft:cow","minecraft:sheep","minecraft:pig","minecraft:chicken").contains(type)
            &&Float.isFinite(health)&&Float.isFinite(maximum)&&maximum>0&&health>=maximum;
    }
    static void require(boolean owned,boolean manual,boolean healthy,boolean exact,boolean ordinaryBoat,
                        boolean passengersMatch,boolean dryArea,boolean visible,boolean weapon,double distance,double reach){
        if(!owned||manual||!healthy||!exact||!ordinaryBoat||!passengersMatch||!dryArea||!visible||!weapon
                ||!Double.isFinite(distance)||!Double.isFinite(reach)||distance<0||reach<=.2||distance>reach-.2)
            throw new IllegalStateException("Boat recovery requires an exact owned boat, healthy expected passengers and dry landing area");
    }
    static void attack(Minecraft c,JsonObject request,boolean owned,boolean manual){
        var entity=c.level.getEntity(request.get("entity_id").getAsInt());
        if(!(entity instanceof AbstractBoat boat))throw new IllegalStateException("Expected ordinary boat required");
        String type=net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(boat.getType()).toString();
        Set<String> expected=new HashSet<>();var ids=request.getAsJsonArray("expected_passenger_uuids");
        if(ids==null||ids.size()>2)throw new IllegalArgumentException("Exact zero to two villager passenger UUIDs required");
        for(var id:ids){String value=id.getAsString();java.util.UUID.fromString(value);if(!expected.add(value))throw new IllegalArgumentException("Duplicate passenger UUID");}
        Set<String> actual=new HashSet<>();boolean healthyPassengers=true;
        if(request.has("allow_healthy_food_animals")&&(!request.get("allow_healthy_food_animals").isJsonPrimitive()
                ||!request.getAsJsonPrimitive("allow_healthy_food_animals").isBoolean()))throw new IllegalArgumentException("Food animal recovery flag must be boolean");
        boolean allowFood=request.has("allow_healthy_food_animals")&&request.get("allow_healthy_food_animals").getAsBoolean();
        for(var passenger:boat.getPassengers()){
            actual.add(passenger.getUUID().toString());
            boolean valid=passenger instanceof Villager v&&v.isAlive()&&!v.isRemoved()&&!v.isBaby()&&!v.hasCustomName()&&v.getHealth()>=19;
            if(passenger instanceof net.minecraft.world.entity.animal.Animal animal&&animal.isAlive()&&!animal.isRemoved())
                valid |= foodPassenger(net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(animal.getType()).toString(),allowFood,
                    animal.isBaby(),animal.hasCustomName(),animal.getHealth(),animal.getMaxHealth());
            healthyPassengers &= valid;
        }
        var feet=BlockPos.containing(boat.getX(),boat.getY()+.01,boat.getZ());boolean dry=true;
        for(int dx=-2;dx<=2;dx++)for(int dz=-2;dz<=2;dz++){
            var floor=feet.offset(dx,-1,dz);
            var chunk=c.level.getChunkSource().getChunk(floor.getX()>>4,floor.getZ()>>4,net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
            if(!dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence.isServerChunk(c.level,chunk)||!c.level.getBlockState(floor).isFaceSturdy(c.level,floor,net.minecraft.core.Direction.UP)
                    ||!c.level.getFluidState(floor).isEmpty()||c.level.getBlockState(floor).is(net.minecraft.world.level.block.Blocks.MAGMA_BLOCK))dry=false;
            for(int dy=0;dy<3;dy++){
                var cell=feet.offset(dx,dy,dz);var state=c.level.getBlockState(cell);
                String name=net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
                if(!c.level.hasChunkAt(cell)||!state.getCollisionShape(c.level,cell).isEmpty()||!c.level.getFluidState(cell).isEmpty()
                    ||Set.of("minecraft:fire","minecraft:soul_fire","minecraft:sweet_berry_bush","minecraft:wither_rose","minecraft:powder_snow").contains(name))dry=false;
            }
        }
        var held=c.player.getMainHandItem();var hit=boat.position().add(0,boat.getBbHeight()*.5,0);
        require(owned,manual,c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=18&&!c.player.isInWater()&&!c.player.isOnFire()
                &&!c.player.isUsingItem()&&c.player.hurtTime==0&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty(),
            boat.getUUID().toString().equals(request.get("expected_uuid").getAsString())&&boat.isAlive()&&!boat.isRemoved()&&!boat.hasCustomName()
                &&!boat.isPassenger()&&(!boat.isLeashed()||boat.getLeashHolder()==c.player),
            (type.endsWith("_boat")||type.equals("minecraft:bamboo_raft"))&&!type.contains("chest"),
            healthyPassengers&&actual.equals(expected)&&boat.getPassengers().size()==expected.size(),dry,
            c.player.hasLineOfSight(boat),(held.is(ItemTags.AXES)||held.is(ItemTags.SWORDS))
                &&(!held.isDamageableItem()||held.getMaxDamage()-held.getDamageValue()>32)&&c.player.getAttackStrengthScale(0)>=.95F,
            c.player.getEyePosition().distanceTo(hit),c.player.entityInteractionRange());
        RotationAim.apply(c.player,RotationAim.lookAt(c.player,hit));
        c.gameMode.attack(c.player,boat);c.player.swing(InteractionHand.MAIN_HAND);
    }
}
