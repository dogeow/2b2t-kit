package dev.twob2tkit.automation;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.resources.RegistryOps;
import net.minecraft.network.protocol.game.ServerboundSelectTradePacket;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.MerchantMenu;
import net.minecraft.world.item.ItemStack;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Read real merchant offers and send ordinary vanilla trade inputs for one exact owner. */
final class VillagerTrading {
    static final int PROTOCOL=1;
    private static Villager actor;
    private static ClientLevel level;
    private static MerchantMenu ownedMenu;
    private static String world="",task="",openingRequest="";
    private static int selected=-1;
    private static long quotedAt;
    private static String quotedFingerprint="";
    private static final Set<UUID> possiblyTraded=new HashSet<>();
    private static final Map<UUID,String> purchaseOpenings=new HashMap<>();
    private record LockedBook(Villager entity,ClientLevel level,String world,String task,long quotedAt){}
    private static final Map<String,LockedBook> lockedBooks=new HashMap<>();
    private static final Map<String,Integer> KEEP_TARGETS=Map.of("minecraft:mending",1,"minecraft:infinity",1,"minecraft:unbreaking",3,
        "minecraft:fortune",3,"minecraft:sharpness",5,"minecraft:efficiency",5,"minecraft:looting",3);

    static void clear(){actor=null;level=null;ownedMenu=null;world=task=openingRequest="";selected=-1;quotedAt=0;quotedFingerprint="";possiblyTraded.clear();purchaseOpenings.clear();lockedBooks.clear();}
    static void opening(Minecraft c,Entity entity,String worldSession,String taskSession,String requestId){
        if(!(entity instanceof Villager v)||v.isBaby()||!v.isAlive()
                ||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()
                ||worldSession.isBlank()||taskSession.isBlank()||requestId.isBlank())
            throw new IllegalStateException("Adult villager and empty original inventory menu required");
        actor=v;level=c.level;world=worldSession;task=taskSession;openingRequest=requestId;ownedMenu=null;selected=-1;quotedAt=0;quotedFingerprint="";
    }
    private static boolean actorCurrent(Minecraft c,String w,String t){
        return actor!=null&&c.level==level&&c.player!=null&&actor.isAlive()
            &&c.level.getEntity(actor.getId())==actor&&world.equals(w)&&task.equals(t)
            &&c.player.distanceToSqr(actor)<=64;
    }
    static boolean adopt(Minecraft c,String w,String t){
        if(!actorCurrent(c,w,t)||!(c.player.containerMenu instanceof MerchantMenu menu))return false;
        if(ownedMenu!=null&&ownedMenu!=menu)return false;
        ownedMenu=menu;return true;
    }
    static boolean owns(Minecraft c,String w,String t){
        return ownedMenu!=null&&c.player!=null&&c.player.containerMenu==ownedMenu&&actorCurrent(c,w,t);
    }
    static JsonObject entity(Villager v){
        var out=new JsonObject();var data=v.getVillagerData();
        out.addProperty("profession",data.profession().unwrapKey().map(k->k.identifier().toString()).orElse("unknown"));
        out.addProperty("biome_type",data.type().unwrapKey().map(k->k.identifier().toString()).orElse("unknown"));
        out.addProperty("level",data.level());
        // Entity XP is a client observation; only the received merchant menu is used to lock trades.
        out.addProperty("entity_xp",v.getVillagerXp());out.addProperty("trade_history_verified",false);
        return out;
    }
    static JsonObject loaded(Minecraft c){
        var out=new JsonObject();var rows=new JsonArray();out.addProperty("protocol",PROTOCOL);
        out.addProperty("scope","current_loaded_client_villagers_only_not_unloaded_chunks");
        if(c.level!=null&&c.player!=null)for(var e:c.level.entitiesForRendering()){
            if(!(e instanceof Villager v)||!v.isAlive()||v.isRemoved()||c.level.getEntity(v.getId())!=v
                    ||!Double.isFinite(v.getX())||!Double.isFinite(v.getY())||!Double.isFinite(v.getZ()))continue;
            var row=new JsonObject();row.addProperty("id",v.getId());row.addProperty("uuid",v.getUUID().toString());
            row.addProperty("type","minecraft:villager");row.addProperty("is_baby",v.isBaby());
            row.addProperty("has_custom_name",v.hasCustomName());row.addProperty("visible",c.player.hasLineOfSight(v));
            row.addProperty("health",v.getHealth());row.addProperty("name",v.getName().getString());
            row.addProperty("distance",c.player.distanceTo(v));
            var pos=new JsonArray();pos.add(v.getX());pos.add(v.getY());pos.add(v.getZ());row.add("pos",pos);
            row.add("villager",entity(v));rows.add(row);if(rows.size()>=256)break;
        }
        out.add("villagers",rows);return out;
    }
    private static JsonObject stack(Minecraft c,ItemStack item){
        var out=AutomationBridge.stack(item);
        out.add("stack_data",ItemStack.OPTIONAL_CODEC.encodeStart(
            RegistryOps.create(JsonOps.INSTANCE,c.player.registryAccess()),item.copy()).getOrThrow());
        return out;
    }
    private static JsonArray offers(Minecraft c,MerchantMenu merchant){
        var offers=new JsonArray();var values=merchant.getOffers();
        if(values.size()>128)throw new IllegalStateException("Merchant offer count exceeds bounded protocol");
        for(int i=0;i<values.size();i++){
            var offer=values.get(i);var row=new JsonObject();row.addProperty("index",i);
            row.add("cost_a",stack(c,offer.getCostA()));row.add("cost_b",stack(c,offer.getCostB()));
            row.add("result",stack(c,offer.getResult()));row.addProperty("uses",offer.getUses());
            row.addProperty("max_uses",offer.getMaxUses());row.addProperty("out_of_stock",offer.isOutOfStock());
            offers.add(row);
        }
        return offers;
    }
    static JsonObject snapshot(Minecraft c,AbstractContainerMenu menu,String w,String t){
        var out=new JsonObject();if(!(menu instanceof MerchantMenu merchant))return out;
        var offers=offers(c,merchant);
        boolean owned=owns(c,w,t);
        out.addProperty("protocol",PROTOCOL);out.addProperty("owned",owned);
        out.addProperty("owner_task",owned?task:"");out.addProperty("villager_uuid",owned?actor.getUUID().toString():"");
        out.addProperty("opening_request_id",owned?openingRequest:"");out.addProperty("menu_id",menu.containerId);
        out.addProperty("level",merchant.getTraderLevel());out.addProperty("trader_xp",merchant.getTraderXp());
        out.addProperty("can_restock",merchant.canRestock());out.add("offers",offers);
        out.addProperty("offers_fingerprint",fingerprint(offers));out.addProperty("requested_index",owned?selected:-1);
        if(owned&&!offers.isEmpty()){
            if(quotedAt==0)quotedAt=System.currentTimeMillis();
            quotedFingerprint=out.get("offers_fingerprint").getAsString();
            if(merchant.getTraderXp()>0&&(!possiblyTraded.contains(actor.getUUID())
                    ||!openingRequest.equals(purchaseOpenings.get(actor.getUUID())))){
                for(var offer:merchant.getOffers()){
                    var stored=offer.getResult().get(net.minecraft.core.component.DataComponents.STORED_ENCHANTMENTS);
                    if(stored!=null)for(var entry:stored.entrySet()){
                        String id=entry.getKey().unwrapKey().map(k->k.identifier().toString()).orElse("");
                        if(KEEP_TARGETS.containsKey(id)&&entry.getIntValue()>=KEEP_TARGETS.get(id))
                            lockedBooks.put(id,new LockedBook(actor,c.level,w,t,quotedAt));
                    }
                }
            }
        }
        out.addProperty("observation_scope","current_server_received_merchant_menu_not_trade_completion");
        return out;
    }
    static void requireSelection(boolean owned,boolean manual,boolean healthy,boolean cursorEmpty,
                                 int actualMenu,int expectedMenu,String actual,String expected,
                                 int index,int count,boolean exhausted){
        if(!owned||manual||!healthy||!cursorEmpty||expectedMenu<=0||actualMenu!=expectedMenu
                ||expected==null||expected.isBlank()||!expected.equals(actual)
                ||index<0||index>=count||exhausted)
            throw new IllegalStateException("Merchant owner, exact offers, selection or stock changed; no packet sent");
    }
    static void select(Minecraft c,JsonObject request,String w,String t,boolean currentOwner,boolean manual){
        var menu=c.player.containerMenu;var info=snapshot(c,menu,w,t);
        int index=request.has("index")?request.get("index").getAsInt():-1;
        int count=info.has("offers")?info.getAsJsonArray("offers").size():0;
        boolean exhausted=index>=0&&index<count&&info.getAsJsonArray("offers").get(index).getAsJsonObject().get("out_of_stock").getAsBoolean();
        requireSelection(currentOwner&&owns(c,w,t),manual,c.player.getHealth()>=19,menu.getCarried().isEmpty(),
            menu.containerId,request.has("menu_id")?request.get("menu_id").getAsInt():-1,
            info.has("offers_fingerprint")?info.get("offers_fingerprint").getAsString():"",
            request.has("expected_offers_fingerprint")?request.get("expected_offers_fingerprint").getAsString():"",
            index,count,exhausted);
        if(!request.has("expected_villager_uuid")||!request.get("expected_villager_uuid").getAsString().equals(actor.getUUID().toString()))
            throw new IllegalStateException("Merchant UUID changed; no packet sent");
        // Vanilla's server handler moves the payment items. Do not fabricate client slots.
        ((MerchantMenu)menu).setSelectionHint(index);
        c.getConnection().send(new ServerboundSelectTradePacket(index));selected=index;
    }
    static void requireOneOutput(String kind,int button,boolean emptyCursor,boolean selectedCurrent,
                                 boolean exactResult,boolean paymentMatches){
        if(!kind.equals("pickup")||button!=0||!emptyCursor||!selectedCurrent||!exactResult||!paymentMatches)
            throw new IllegalStateException("One exact selected trade requires an empty-cursor left pickup; no bulk purchase sent");
    }
    static void beforeClick(Minecraft c,JsonObject request,String w,String t,boolean currentOwner){
        if(!(c.player.containerMenu instanceof MerchantMenu menu))return;
        if(!currentOwner||!owns(c,w,t))throw new IllegalStateException("Foreign merchant menu; no inventory click sent");
        int slot=request.get("slot").getAsInt();if(slot!=2)return;
        var info=snapshot(c,menu,w,t);String expected=request.has("expected_offers_fingerprint")?request.get("expected_offers_fingerprint").getAsString():"";
        requireSelection(true,false,c.player.getHealth()>=19,menu.getCarried().isEmpty(),menu.containerId,
            request.get("menu_id").getAsInt(),info.get("offers_fingerprint").getAsString(),expected,
            selected,menu.getOffers().size(),selected>=0&&selected<menu.getOffers().size()&&menu.getOffers().get(selected).isOutOfStock());
        var offer=menu.getOffers().get(selected);
        requireOneOutput(request.get("kind").getAsString(),request.get("button").getAsInt(),menu.getCarried().isEmpty(),
            request.has("expected_trade_index")&&request.get("expected_trade_index").getAsInt()==selected,
            ItemStack.matches(menu.getSlot(2).getItem(),offer.getResult()),
            offer.satisfiedBy(menu.getSlot(0).getItem(),menu.getSlot(1).getItem()));
        // Fence a possible purchase before its normal output click is dispatched.
        possiblyTraded.add(actor.getUUID());
        purchaseOpenings.put(actor.getUUID(),openingRequest);
    }
    static boolean protectUsefulBook(boolean requested,boolean allowDuplicate,boolean verifiedOther){return requested&&(!allowDuplicate||!verifiedOther);}
    private static boolean lockedElsewhere(Minecraft c,String id,String w,String t){
        var book=lockedBooks.get(id);
        return book!=null&&book.level==c.level&&book.world.equals(w)&&book.task.equals(t)&&book.entity!=actor
            &&System.currentTimeMillis()-book.quotedAt>=0&&System.currentTimeMillis()-book.quotedAt<=30000
            &&book.entity.isAlive()&&!book.entity.isRemoved()&&!book.entity.isBaby()
            &&c.level.getEntity(book.entity.getId())==book.entity&&c.player.distanceToSqr(book.entity)<=48*48
            &&book.entity.getVillagerData().profession().unwrapKey().map(k->k.identifier().toString().equals("minecraft:librarian")).orElse(false);
    }
    static void requireResetPolicy(boolean owned,boolean inventoryOnly,boolean fresh,boolean exactQuote,
                                   int level,int xp,boolean used,boolean valuable,boolean emptyLectern,boolean nearby){
        if(!owned||!inventoryOnly||!fresh||!exactQuote||level!=1||xp!=0||used||valuable||!emptyLectern||!nearby)
            throw new IllegalStateException("Lectern reset requires an empty lectern beside the same freshly quoted untraded librarian without a requested book");
    }
    static void requireEmptyLecternReset(Minecraft c,JsonObject request,net.minecraft.core.BlockPos pos,String w,String t,boolean owned){
        boolean current=actorCurrent(c,w,t);boolean empty=c.level.getBlockEntity(pos) instanceof net.minecraft.world.level.block.entity.LecternBlockEntity lectern
            &&!lectern.hasBook()&&lectern.getBook().isEmpty()
            &&c.level.getBlockState(pos).is(net.minecraft.world.level.block.Blocks.LECTERN)
            &&!c.level.getBlockState(pos).getValue(net.minecraft.world.level.block.LecternBlock.HAS_BOOK);
        boolean exact=current&&ownedMenu!=null&&request.has("expected_villager_uuid")
            &&actor.getUUID().toString().equals(request.get("expected_villager_uuid").getAsString())
            &&request.has("expected_quote_opening")&&openingRequest.equals(request.get("expected_quote_opening").getAsString())
            &&request.has("expected_offers_fingerprint")&&!quotedFingerprint.isBlank()
            &&quotedFingerprint.equals(request.get("expected_offers_fingerprint").getAsString())
            &&quotedFingerprint.equals(fingerprint(offers(c,ownedMenu)));
        boolean used=current&&possiblyTraded.contains(actor.getUUID()),valuable=false;
        if(request.has("allow_verified_duplicate_reset")&&(!request.get("allow_verified_duplicate_reset").isJsonPrimitive()
                ||!request.getAsJsonPrimitive("allow_verified_duplicate_reset").isBoolean()))throw new IllegalArgumentException("Duplicate book reset flag must be boolean");
        boolean allowDuplicate=request.has("allow_verified_duplicate_reset")&&request.get("allow_verified_duplicate_reset").getAsBoolean();
        if(ownedMenu!=null)for(var offer:ownedMenu.getOffers()){
            used |= offer.getUses()!=0;
            var stored=offer.getResult().get(net.minecraft.core.component.DataComponents.STORED_ENCHANTMENTS);
            if(stored!=null)for(var entry:stored.entrySet()){
                String id=entry.getKey().unwrapKey().map(k->k.identifier().toString()).orElse("");
                if(protectUsefulBook(KEEP_TARGETS.containsKey(id)&&entry.getIntValue()>=KEEP_TARGETS.get(id),allowDuplicate,lockedElsewhere(c,id,w,t)))valuable=true;
            }
        }
        boolean librarian=current&&actor.getVillagerData().profession().unwrapKey()
            .map(k->k.identifier().toString().equals("minecraft:librarian")).orElse(false);
        requireResetPolicy(owned&&current&&librarian,c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty(),
            quotedAt>0&&System.currentTimeMillis()-quotedAt>=0&&System.currentTimeMillis()-quotedAt<=30000,
            exact&&ownedMenu!=null&&!ownedMenu.getOffers().isEmpty()&&ownedMenu.canRestock(),ownedMenu==null?-1:ownedMenu.getTraderLevel(),
            ownedMenu==null?-1:ownedMenu.getTraderXp(),used,valuable,empty,
            current&&actor.position().distanceTo(net.minecraft.world.phys.Vec3.atBottomCenterOf(pos))<=1.9);
    }
    static String fingerprint(JsonElement value){
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical(value).toString().getBytes(StandardCharsets.UTF_8)));}
        catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
    }
    private static JsonElement canonical(JsonElement v){
        if(v.isJsonObject()){
            var out=new JsonObject();new TreeMap<>(v.getAsJsonObject().asMap()).forEach((k,e)->out.add(k,canonical(e)));return out;
        }
        if(v.isJsonArray()){var out=new JsonArray();v.getAsJsonArray().forEach(e->out.add(canonical(e)));return out;}
        return v.deepCopy();
    }
}
