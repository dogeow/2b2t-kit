package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.saveddata.maps.MapId;
import net.minecraft.world.level.saveddata.maps.MapItemSavedData;
import java.util.Map;
import java.util.TreeMap;

/** Narrow normal-interaction map API; all reads stay in the current client world. */
final class MapAutomation {
    private MapAutomation() {}
    enum Outcome { RUNNING,DONE,WAITING }

    static void addItemDetails(JsonObject target,ItemStack item) {
        var id=item.get(DataComponents.MAP_ID);if(id==null)return;
        target.addProperty("map_id",id.id());
        var c=Minecraft.getInstance();var data=c.level==null?null:c.level.getMapData(id);
        target.addProperty("map_data_loaded",data!=null);
        if(data!=null)target.add("map",metadata(id,data));
    }

    private static JsonObject metadata(MapId id,MapItemSavedData data) {
        var out=new JsonObject();out.addProperty("map_id",id.id());out.addProperty("scale",data.scale);
        out.addProperty("locked",data.locked);out.addProperty("center_x",data.centerX);out.addProperty("center_z",data.centerZ);
        out.addProperty("dimension",data.dimension.identifier().toString());
        // Vanilla ClientboundMapItemDataPacket transmits neither center nor dimension.
        // createForClient initializes centers to zero and assigns the current dimension.
        out.addProperty("geographic_center_verified",false);out.addProperty("geographic_dimension_verified",false);
        out.addProperty("geography_source","client_cache_placeholder_not_server_geographic_metadata");
        return out;
    }

    private static int requestInteger(JsonObject request,String key) {
        var value=request.get(key);
        if(value==null||!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())
            throw new IllegalArgumentException(key+" must be a nonnegative integer");
        double number=value.getAsDouble();
        if(!Double.isFinite(number)||number!=Math.rint(number)||number<0||number>Integer.MAX_VALUE)
            throw new IllegalArgumentException(key+" must be a nonnegative integer");
        return (int)number;
    }

    static JsonObject audit(Minecraft c,JsonObject request) {
        if(c.player==null||c.level==null)throw new IllegalStateException("Map audit requires the current loaded world");
        ItemStack stack=c.player.getMainHandItem();
        if(request.has("slot")) {
            int slot=requestInteger(request,"slot");
            if(slot<0||slot>=c.player.getInventory().getContainerSize())throw new IllegalArgumentException("Invalid current inventory slot");
            stack=c.player.getInventory().getItem(slot);
        } else if(request.has("map_id")) {
            int wanted=requestInteger(request,"map_id");stack=ItemStack.EMPTY;
            for(int i=0;i<c.player.getInventory().getContainerSize();i++) {
                var candidate=c.player.getInventory().getItem(i);var id=candidate.get(DataComponents.MAP_ID);
                if(!candidate.isEmpty()&&candidate.is(Items.FILLED_MAP)&&id!=null&&id.id()==wanted){stack=candidate;break;}
            }
        }
        var id=stack.get(DataComponents.MAP_ID);
        if(stack.isEmpty()||!stack.is(Items.FILLED_MAP)||id==null)
            throw new IllegalStateException("Expected a filled map in the current inventory");
        if(request.has("map_id")&&id.id()!=requestInteger(request,"map_id"))
            throw new IllegalStateException("Current filled map ID changed");
        var data=c.level.getMapData(id);
        if(data==null)throw new IllegalStateException("Map data is not loaded in the current client world; hold this map and wait for a server update");
        var out=metadata(id,data);out.addProperty("audit_schema",1);out.addProperty("observed_at",System.currentTimeMillis());
        out.add("colors",MapAuditCodec.colors(data.colors));return out;
    }

    private static int emptyCount(Minecraft c) {
        int count=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++) {
            var item=c.player.getInventory().getItem(i);if(item.is(Items.MAP))count+=item.getCount();
        }return count;
    }
    private static Map<Integer,Integer> filledCounts(Minecraft c) {
        var counts=new TreeMap<Integer,Integer>();
        for(int i=0;i<c.player.getInventory().getContainerSize();i++) {
            var item=c.player.getInventory().getItem(i);if(item.isEmpty()||!item.is(Items.FILLED_MAP))continue;
            var id=item.get(DataComponents.MAP_ID);
            if(id==null)throw new IllegalStateException("A filled map is missing MAP_ID; inventory evidence is ambiguous");
            counts.merge(id.id(),item.getCount(),Integer::sum);
        }return counts;
    }

    static final class Creation {
        private final int beforeEmpty,selectedSlot;
        private final Map<Integer,Integer> beforeFilled;
        private final float health;
        private final int centerX,centerZ;
        private final String worldSession,requestId,dimension;
        private int afterEmpty,createdId=-1;
        private boolean useSent;

        Creation(Minecraft c,String world,String id,JsonObject request) {
            if(c.player==null||c.level==null||c.gameMode==null||c.player.isDeadOrDying()
                ||c.player.hasInfiniteMaterials()||c.screen!=null||c.player.containerMenu!=c.player.inventoryMenu
                ||!c.player.containerMenu.getCarried().isEmpty()||c.player.isUsingItem()
                ||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire()
                ||c.options.keyUse.isDown()||!c.player.getMainHandItem().is(Items.MAP))
                throw new IllegalStateException("Map creation requires an idle survival inventory with an empty map held in the main hand");
            int free=0;for(int i=0;i<Math.min(36,c.player.getInventory().getContainerSize());i++)
                if(c.player.getInventory().getItem(i).isEmpty())free++;
            if(!MapCreationPolicy.canReceive(c.player.getMainHandItem().getCount(),free))
                throw new IllegalStateException("No free main inventory slot for the created map; result would be dropped");
            centerX=MapCreationPolicy.scaleZeroCenter(c.player.getX());centerZ=MapCreationPolicy.scaleZeroCenter(c.player.getZ());
            if(request.has("expected_center")) {
                var expected=request.getAsJsonArray("expected_center");
                if(expected==null||expected.size()!=2||expected.get(0).getAsDouble()!=centerX||expected.get(1).getAsDouble()!=centerZ)
                    throw new IllegalStateException("Player position does not belong to the expected scale-zero map grid");
            }
            selectedSlot=c.player.getInventory().getSelectedSlot();beforeEmpty=afterEmpty=emptyCount(c);
            beforeFilled=filledCounts(c);health=c.player.getHealth();worldSession=world;requestId=id;
            dimension=c.level.dimension().identifier().toString();
        }

        void useOnce(Minecraft c) {
            if(useSent)throw new IllegalStateException("Map creation use was already sent; no retry is allowed");
            useSent=true;
            if(!c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND).consumesAction())
                throw new IllegalStateException("One map use was sent but not accepted; inspect inventory, never retry automatically");
        }

        Outcome poll(Minecraft c,boolean timedOut) {
            afterEmpty=emptyCount(c);
            if(!useSent||c.player.getHealth()<health||c.player.getInventory().getSelectedSlot()!=selectedSlot
                ||c.screen!=null||c.player.containerMenu!=c.player.inventoryMenu
                ||!c.player.containerMenu.getCarried().isEmpty())return Outcome.WAITING;
            createdId=MapCreationPolicy.confirmedId(beforeEmpty,afterEmpty,beforeFilled,filledCounts(c));
            if(createdId>=0)return Outcome.DONE;
            return timedOut?Outcome.WAITING:Outcome.RUNNING;
        }

        JsonObject snapshot(boolean confirmed) {
            var out=new JsonObject();out.addProperty("request_id",requestId);out.addProperty("world_session",worldSession);
            out.addProperty("use_count",useSent?1:0);out.addProperty("empty_maps_before",beforeEmpty);out.addProperty("empty_maps_after",afterEmpty);
            out.addProperty("inventory_delta_confirmed",confirmed&&createdId>=0);
            if(createdId>=0)out.addProperty("map_id",createdId);
            out.addProperty("expected_creation_center_x",centerX);out.addProperty("expected_creation_center_z",centerZ);
            out.addProperty("expected_creation_scale",0);out.addProperty("expected_creation_dimension",dimension);
            out.addProperty("creation_geography_source","normal_game_use_position_grid_prediction_not_server_map_metadata");
            out.addProperty("confirmation_scope","exact_minus_one_empty_plus_one_new_map_id_in_current_inventory");
            out.addProperty("automatic_retry_allowed",false);return out;
        }
    }
}
