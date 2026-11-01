package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.state.properties.ChestType;
import java.util.List;

/** One-use server-empty proof for repairing two projection-required single chest halves. */
final class EmptyChestRecovery {
    private static Object connection,level;
    private static BlockPos target;
    private static String task="";
    private static AbstractContainerMenu menu;
    private static boolean seen;
    private static final int[] counts=new int[27];
    private static long serial,expires;
    private EmptyChestRecovery(){}
    static boolean allowed(boolean owned,boolean exactMenu,boolean serverSeen,boolean serverEmpty,
                           boolean clientEmpty,boolean cursorEmpty,boolean projectionPair,
                           boolean safeTool,boolean pickupRoom,boolean healthy,boolean dryIsolated,
                           boolean otherPlayer,long remaining) {
        return owned&&exactMenu&&serverSeen&&serverEmpty&&clientEmpty&&cursorEmpty&&projectionPair
            &&safeTool&&pickupRoom&&healthy&&dryIsolated&&!otherPlayer&&remaining>0&&remaining<=30_000;
    }
    static void clear(){connection=level=null;target=null;task="";menu=null;seen=false;expires=0;}
    static void opening(Minecraft c,String owner,BlockPos pos){
        clear();if(owner.isEmpty()||c.player==null||c.level==null||c.player.containerMenu!=c.player.inventoryMenu)return;
        var state=c.level.getBlockState(pos);if(!state.is(Blocks.CHEST)||state.getValue(ChestBlock.TYPE)!=ChestType.SINGLE)return;
        connection=c.getConnection();level=c.level;target=pos.immutable();task=owner;expires=System.currentTimeMillis()+30_000;
    }
    private static boolean current(Minecraft c,Object sender,int id){
        return target!=null&&sender==connection&&c.getConnection()==connection&&c.level==level
            &&c.player!=null&&c.player.containerMenu instanceof ChestMenu cm&&cm.getRowCount()==3&&cm.containerId==id
            &&System.currentTimeMillis()<expires;
    }
    static void content(Minecraft c,Object sender,int id,List<ItemStack> items){
        if(!current(c,sender,id)||items.size()!=63)return;
        menu=c.player.containerMenu;for(int i=0;i<27;i++)counts[i]=items.get(i).getCount();seen=true;serial++;
    }
    static void slot(Minecraft c,Object sender,int id,int slot,ItemStack item){
        if(!current(c,sender,id)||!seen||menu!=c.player.containerMenu||slot<0||slot>=27)return;
        counts[slot]=item.getCount();serial++;
    }
    private static boolean serverEmpty(){for(int n:counts)if(n!=0)return false;return true;}
    static JsonObject snapshot(Minecraft c){
        var out=new JsonObject();boolean exact=target!=null&&c.player!=null&&c.getConnection()==connection&&c.level==level&&c.player.containerMenu==menu&&System.currentTimeMillis()<expires;
        out.addProperty("server_content_seen",exact&&seen);out.addProperty("server_slots_empty",exact&&seen&&serverEmpty());out.addProperty("content_serial",serial);out.addProperty("menu_id",exact?menu.containerId:-1);
        if(target!=null)out.addProperty("target",target.toShortString());return out;
    }
    private static boolean pair(Minecraft c,JsonObject request,BlockPos pos){
        var selected=dev.twob2tkit.builder.LitematicaAccess.lockedBuildSelection();
        if(!request.has("placement_key")||!selected.key().equals(request.get("placement_key").getAsString())||!selected.contains(pos)
                ||!dev.twob2tkit.builder.LitematicaAccess.loadingReason(selected).isEmpty())return false;
        var model=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();if(model==null)return false;
        var actual=c.level.getBlockState(pos);var goal=model.getBlockState(pos);
        if(!actual.is(Blocks.CHEST)||!goal.is(Blocks.CHEST)||actual.getValue(ChestBlock.TYPE)!=ChestType.SINGLE
                ||goal.getValue(ChestBlock.TYPE)==ChestType.SINGLE||actual.getValue(ChestBlock.WATERLOGGED)||goal.getValue(ChestBlock.WATERLOGGED)
                ||actual.getValue(ChestBlock.FACING)!=goal.getValue(ChestBlock.FACING))return false;
        BlockPos other=pos.relative(ChestBlock.getConnectedDirection(goal));
        if(!selected.contains(other)||!c.level.hasChunkAt(other))return false;
        var peer=c.level.getBlockState(other);var peerGoal=model.getBlockState(other);
        return peer.is(Blocks.CHEST)&&peerGoal.is(Blocks.CHEST)&&peer.getValue(ChestBlock.TYPE)==ChestType.SINGLE
            &&peerGoal.getValue(ChestBlock.TYPE)!=ChestType.SINGLE&&!peer.getValue(ChestBlock.WATERLOGGED)&&!peerGoal.getValue(ChestBlock.WATERLOGGED)
            &&peerGoal.getValue(ChestBlock.TYPE)!=goal.getValue(ChestBlock.TYPE)
            &&peer.getValue(ChestBlock.FACING)==actual.getValue(ChestBlock.FACING)
            &&peerGoal.getValue(ChestBlock.FACING)==goal.getValue(ChestBlock.FACING)
            &&other.relative(ChestBlock.getConnectedDirection(peerGoal)).equals(pos);
    }
    private static boolean dryIsolated(Minecraft c,BlockPos pos){
        for(Direction d:Direction.values()){
            var p=pos.relative(d);if(!c.level.hasChunkAt(p)||!c.level.getFluidState(p).isEmpty())return false;
            var state=c.level.getBlockState(p);if(state.is(Blocks.HOPPER)||state.is(Blocks.DROPPER)||state.is(Blocks.DISPENSER))return false;
        }return true;
    }
    private static boolean otherPlayer(Minecraft c,BlockPos pos){return c.level.players().stream().anyMatch(p->p!=c.player&&p.isAlive()&&p.position().distanceToSqr(net.minecraft.world.phys.Vec3.atCenterOf(pos))<=64);}
    private static boolean tool(ItemStack stack){return stack.is(net.minecraft.tags.ItemTags.AXES)&&stack.isDamageableItem()&&stack.getMaxDamage()-stack.getDamageValue()>=32;}
    static void prepare(Minecraft c,JsonObject request,BlockPos pos,boolean owned){
        int slot=request.get("tool_slot").getAsInt();if(slot<0||slot>=9)throw new IllegalArgumentException("Chest repair requires an observed hotbar axe");
        var current=c.player.containerMenu;boolean exact=target!=null&&target.equals(pos)&&task.equals(request.get("task_session").getAsString())&&c.level==level&&c.getConnection()==connection&&menu==current&&current instanceof ChestMenu cm&&cm.getRowCount()==3&&current.containerId==request.get("expected_menu_id").getAsInt()&&serial==request.get("expected_content_serial").getAsLong();
        boolean empty=current instanceof ChestMenu cm&&cm.getRowCount()==3;for(int i=0;i<27&&empty;i++)empty=!current.getSlot(i).hasItem();
        boolean transientEmpty=current.getCarried().isEmpty();for(int i=0;i<5;i++)transientEmpty&=!c.player.inventoryMenu.getSlot(i).hasItem();
        if(!allowed(owned,exact,seen,serverEmpty(),empty,transientEmpty,pair(c,request,pos),tool(c.player.getInventory().getItem(slot)),c.player.getInventory().getFreeSlot()>=0,c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=18,dryIsolated(c,pos),otherPlayer(c,pos),expires-System.currentTimeMillis()))
            throw new IllegalStateException("Chest repair requires the current server-empty single menu, matching projection pair, dry isolated surroundings, axe and pickup room");
        clear();c.player.closeContainer();c.player.getInventory().setSelectedSlot(slot);
    }
    static void validateMining(Minecraft c,JsonObject request,BlockPos pos){
        if(c.player.getInventory().getSelectedSlot()!=request.get("tool_slot").getAsInt()||!tool(c.player.getMainHandItem())||c.player.getInventory().getFreeSlot()<0||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<18||!pair(c,request,pos)||!dryIsolated(c,pos)||otherPlayer(c,pos))
            throw new IllegalStateException("Empty single chest repair context changed; mining stopped");
    }
}
