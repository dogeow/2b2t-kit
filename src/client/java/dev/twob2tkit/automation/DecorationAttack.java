package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.decoration.ItemFrame;
import net.minecraft.world.entity.decoration.painting.Painting;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.runtime.api.RotationAim;

/** One ordinary hit at an exact observed decoration in the current original placement. */
final class DecorationAttack {
 private DecorationAttack(){}
 static void attack(Minecraft c,JsonObject r,boolean owned,boolean manual) throws Exception{
  var entity=c.level.getEntity(r.get("entity_id").getAsInt());
  if(entity==null||!entity.getUUID().toString().equals(r.get("expected_uuid").getAsString()))throw new IllegalStateException("Decoration identity changed");
  String type=BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString();boolean empty=true;
  if(entity instanceof ItemFrame frame)empty=frame.getItem().isEmpty();
  if(entity instanceof ArmorStand stand)for(var slot:new EquipmentSlot[]{EquipmentSlot.MAINHAND,EquipmentSlot.OFFHAND,EquipmentSlot.HEAD,EquipmentSlot.CHEST,EquipmentSlot.LEGS,EquipmentSlot.FEET})empty&=stand.getItemBySlot(slot).isEmpty();
  if(!DecorationAttackPolicy.target(type,r.get("expected_type").getAsString(),entity.isAlive(),entity.isRemoved(),entity.hasCustomName(),empty)
      ||!owned||manual||c.player.getHealth()<19||c.player.isUnderWater()||c.player.getAttackStrengthScale(0)<.95)
   throw new IllegalStateException("Expected empty owned-work decoration and healthy current material scope required");
  var selected=dev.twob2tkit.builder.LitematicaAccess.buildSelection();
  if(!selected.key().equals(r.get("placement_key").getAsString()))throw new IllegalStateException("Original placement changed");
  var expected=r.getAsJsonArray("expected_pos");if(expected==null||expected.size()!=3)throw new IllegalArgumentException("Exact observed decoration position required");
  var pos=new Vec3(expected.get(0).getAsDouble(),expected.get(1).getAsDouble(),expected.get(2).getAsDouble());
  if(!Double.isFinite(pos.x)||!Double.isFinite(pos.y)||!Double.isFinite(pos.z)||entity.position().distanceToSqr(pos)>.015625
      ||pos.x<selected.min().getX()||pos.x>selected.max().getX()+1||pos.y<selected.min().getY()||pos.y>selected.max().getY()+1||pos.z<selected.min().getZ()||pos.z>selected.max().getZ()+1)
   throw new IllegalStateException("Decoration moved or lies outside the original placement");
  if(entity instanceof Painting painting){
   String variant=painting.getVariant().unwrapKey().map(k->k.identifier().toString()).orElse("unregistered");
   if(!r.has("expected_variant")||!variant.equals(r.get("expected_variant").getAsString()))throw new IllegalStateException("Painting variant changed");
  }
  var aim=entity.position().add(0,entity.getBbHeight()*.5,0);
  if(c.player.getEyePosition().distanceTo(aim)>c.player.entityInteractionRange()-.1||!c.player.hasLineOfSight(entity))throw new IllegalStateException("Decoration out of reach or occluded");
  RotationAim.apply(c.player,RotationAim.lookAt(c.player,aim));c.gameMode.attack(c.player,entity);c.player.swing(InteractionHand.MAIN_HAND);
 }
}
