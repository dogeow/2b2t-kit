package dev.twob2tkit.concrete;

import com.google.gson.JsonObject;
import dev.twob2tkit.*;
import dev.twob2tkit.automation.PlacementRotation;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.component.DataComponents;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ServerboundPlayerInputPacket;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.player.Input;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.*;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;
import java.util.*;

/** One real placement / hardening / mining loop. Never retargets nearby blocks or containers. */
public final class ConcreteMaker {
    private final KitConfig config;
    private final ConcreteConfirmation confirmation=new ConcreteConfirmation();
    private boolean active, breaking, submitted, pending, mineStarted;
    private int completed, ticks, stateSince, pendingSince, emptyTicks, lastSlot=-1, originalSlot=-1, powderSlot=-1, failures;
    private long generation;
    private ClientLevel level;
    private BlockPos target, anchor;
    private BlockHitResult placement;
    private BlockState anchorState;
    private Item powder;
    private Block solid;
    private Vec3 start;
    private String status="手持混凝土粉末，瞄准放置面后开始";
    private final Set<String> pausedModules=new HashSet<>();
    private static final String AUTO_TOOL="meteordevelopment.meteorclient.systems.modules.player.AutoTool";
    private static final String AUTO_WEAPON="meteordevelopment.meteorclient.systems.modules.combat.AutoWeapon";
    public ConcreteMaker(KitConfig config){this.config=config;}
    public boolean isActive(){return active;}
    public boolean ownsMining(){return active && mineStarted;}
    public String status(){return status+(completed>0 ? " · 已挖 "+completed+" 块" : "");}
    public JsonObject snapshot(){var j=new JsonObject();j.addProperty("active",active);j.addProperty("completed",completed);j.addProperty("status",status());if(target!=null)j.addProperty("target",target.toShortString());return j;}
    private static String id(Item item){return BuiltInRegistries.ITEM.getKey(item).toString();}
    public boolean start(Minecraft c){
        try{return begin(c);}catch(Exception e){return fail(e.getMessage()==null?"无法检查制作条件":e.getMessage());}
    }
    private boolean begin(Minecraft c){
        if(c.player==null || c.level==null || c.gameMode==null)return fail("请先进入世界");
        var hand=c.player.getMainHandItem();String color=ConcretePolicy.solidId(id(hand.getItem()));
        if(color==null)return fail("请先在主手拿混凝土粉末，再瞄准放置面");
        if(!(c.player.pick(c.player.blockInteractionRange(),1,false) instanceof BlockHitResult hit) || hit.getType()!=HitResult.Type.BLOCK)return fail("准星需要指向漏斗顶面或固定支撑面");
        Block match=BuiltInRegistries.BLOCK.getValue(net.minecraft.resources.Identifier.parse(color));
        BlockState pointed=c.level.getBlockState(hit.getBlockPos());
        BlockPos cell;
        if(pointed.is(match) || pointed.is(Block.byItem(hand.getItem()))){
            cell=hit.getBlockPos();anchor=cell.below();
            placement=new BlockHitResult(Vec3.atCenterOf(anchor).add(0,.5,0),Direction.UP,anchor,false);
        }else{
            anchor=hit.getBlockPos();placement=hit;cell=anchor.relative(hit.getDirection());
        }
        var cellState=c.level.getBlockState(cell);
        if(!cellState.isAir() && !cellState.is(Blocks.WATER) && !cellState.is(match) && !cellState.is(Block.byItem(hand.getItem())))return fail("放置位置已被其它方块占用");
        if(c.player.getBoundingBox().intersects(new AABB(cell)))return fail("放置位置与身体重叠，请稍微退后");
        if(c.level.getBlockState(cell.below()).getCollisionShape(c.level,cell.below()).isEmpty())return fail("粉末下方需要漏斗或其它支撑，避免粉末下落");
        boolean water=false;for(Direction d:Direction.values())if(d!=Direction.DOWN && c.level.getFluidState(cell.relative(d)).is(FluidTags.WATER))water=true;
        if(!water && !cellState.is(match) && !cellState.is(Blocks.WATER))return fail("放置位置旁没有水；含水树叶也可以");
        if(selectTool(c,match.defaultBlockState(),false)<0)return fail("背包没有耐久足够、能采集混凝土的镐");
        if(c.player.getHealth()<Math.max(8,config.minHealth))return fail("血量过低，请先恢复");
        target=cell.immutable();anchor=anchor.immutable();anchorState=c.level.getBlockState(anchor);
        powder=hand.getItem();solid=match;start=c.player.position();level=c.level;
        originalSlot=c.player.getInventory().getSelectedSlot();powderSlot=originalSlot;lastSlot=-1;
        active=true;breaking=submitted=pending=mineStarted=false;completed=ticks=stateSince=emptyTicks=failures=0;generation++;
        confirmation.reset(cellState.is(match));status="已锁定 "+target.toShortString();log(c,"start powder="+id(powder));return true;
    }
    public void serverBlock(BlockPos pos,BlockState state){
        if(active && pos.equals(target) && Minecraft.getInstance().level==level)
            confirmation.observe(state.is(solid),state.isAir() || state.is(Blocks.WATER));
    }
    private boolean fail(String reason){status=reason;return false;}
    public void stop(Minecraft c,String reason){
        if(!active)return;
        active=false;generation++;pause(c);restoreToolSlots(c);
        if(c.player!=null && c.player.getInventory().getSelectedSlot()==lastSlot && originalSlot>=0)c.player.getInventory().setSelectedSlot(originalSlot);
        status="已停止："+reason;log(c,"stop reason="+reason);
    }
    /** Yield before Meteor eats or the shared bow guard acquires its input. */
    public void pause(Minecraft c){
        if(pending){pending=false;generation++;}
        if(breaking && c.gameMode!=null)c.gameMode.stopDestroyBlock();
        mineStarted=false;
        releaseModules();
        // This module never holds Use/Attack/Sneak across ticks; manual and food input stay untouched.
    }
    private void releaseModules(){for(String m:pausedModules)MeteorModules.enable(m);pausedModules.clear();}
    private void acquireTools(){for(String m:List.of(AUTO_TOOL,AUTO_WEAPON))if(MeteorModules.disable(m))pausedModules.add(m);}
    private static boolean eating(Minecraft c){
        if(c.player.isUsingItem() && c.player.getUseItem().has(DataComponents.FOOD))return true;
        try{
            Class<?> registry=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");Object modules=registry.getMethod("get").invoke(null);
            Object eat=registry.getMethod("get",Class.class).invoke(modules,Class.forName("meteordevelopment.meteorclient.systems.modules.player.AutoEat"));
            return eat!=null && (boolean)eat.getClass().getMethod("isActive").invoke(eat) && (eat.getClass().getField("eating").getBoolean(eat) || (boolean)eat.getClass().getMethod("shouldEat").invoke(eat));
        }catch(ClassNotFoundException absent){return false;}catch(ReflectiveOperationException e){throw new IllegalStateException("无法读取自动吃状态",e);}
    }
    public void tick(Minecraft c){
        if(!active)return;
        try{
            if(c.player==null || c.level!=level || c.gameMode==null || c.player.isDeadOrDying()){stop(c,"离开原世界");return;}
            if(c.player.position().distanceTo(start)>.8){stop(c,"角色已离开固定制作位置");return;}
            if(c.screen!=null){pause(c);stateSince=ticks;status="界面打开，暂停制作";return;}
            if(c.player.getHealth()<Math.max(8,config.minHealth)){stop(c,"血量不足");return;}
            if(eating(c)){pause(c);stateSince=ticks;status="等待自动吃完成";return;}
            if(!c.level.getBlockState(anchor).equals(anchorState)){stop(c,"支撑面发生变化");return;}
            ticks++;
            if(pending && ticks-pendingSince>40){stop(c,"等待视角同步超时");return;}
            BlockState s=c.level.getBlockState(target);
            ConcretePolicy.Cell cell=s.is(solid)?ConcretePolicy.Cell.CONCRETE:s.is(Block.byItem(powder))?ConcretePolicy.Cell.POWDER:s.isAir()||s.is(Blocks.WATER)?ConcretePolicy.Cell.EMPTY:ConcretePolicy.Cell.FOREIGN;
            var action=ConcretePolicy.action(cell,breaking,submitted);
            if(action==ConcretePolicy.Action.STOP || c.level.getBlockEntity(target)!=null){stop(c,"目标变成了其它方块，已保护现场");return;}
            if(action==ConcretePolicy.Action.VERIFY_BREAK){
                c.gameMode.stopDestroyBlock();
                if(!confirmation.removed()){status="等待服务器确认挖除";if(ticks-stateSince>160)stop(c,"服务器未确认挖除，请检查权限或网络");return;}
                if(++emptyTicks<8){status="等待方块移除确认";return;}
                completed++;confirmation.reset(false);breaking=submitted=mineStarted=false;emptyTicks=0;stateSince=ticks;failures=0;
                if(completed==1 || completed%16==0)log(c,"progress");
                if(ConcretePolicy.reached(completed,config.concreteLimit)){stop(c,"达到设定数量");return;}
                status="准备下一块";return;
            }
            emptyTicks=0;
            if(action==ConcretePolicy.Action.WAIT_WATER){
                status="等待粉末遇水硬化";
                if(ticks-stateSince>80)stop(c,"粉末未在固定位置变成混凝土，请检查水和支撑");
                return;
            }
            if(action==ConcretePolicy.Action.PLACE){
                if(ticks-stateSince<Math.clamp(config.concreteDelayTicks,2,40) || pending)return;
                if(selectPowder(c)<0){stop(c,"同色粉末已用完");return;}
                acquireTools();
                if(c.player.getBoundingBox().intersects(new AABB(target))){stop(c,"身体挡住了放置位置");return;}
                if(c.player.getEyePosition().distanceTo(placement.getLocation())>c.player.blockInteractionRange()-.1){stop(c,"放置面超出距离");return;}
                long token=generation;pending=true;pendingSince=ticks;var look=RotationAim.lookAt(c.player,placement.getLocation());
                PlacementRotation.after(c,look.yaw(),look.pitch(),()->{
                    if(!active || token!=generation)return;pending=false;
                    if(c.screen!=null || c.level!=level || dev.twob2tkit.automation.AutomationBridge.guardBusy())return;
                    var current=c.level.getBlockState(target);
                    if(!current.isAir() && !current.is(Blocks.WATER))return;
                    if(!c.player.getMainHandItem().is(powder))return;
                    if(c.player.position().distanceTo(start)>.8 || !c.level.getBlockState(anchor).equals(anchorState)){stop(c,"放置前现场发生变化");return;}
                    placeSneaking(c);submitted=true;stateSince=ticks;status="粉末已放置，等待硬化";
                });
                return;
            }
            if(!confirmation.canMine()){status="等待服务器确认混凝土";if(ticks-stateSince>80)stop(c,"服务器未确认放置，请检查权限或网络");return;}
            // No other coordinate or block type can reach the mining API.
            acquireTools();int tool=selectTool(c,s,true);
            if(tool<0){stop(c,"没有耐久足够的可用镐");return;}
            var eye=c.player.getEyePosition();var aim=Vec3.atCenterOf(target);
            if(eye.distanceTo(aim)>c.player.blockInteractionRange()-.1){stop(c,"混凝土超出距离");return;}
            var hit=c.level.clip(new ClipContext(eye,aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(!hit.getBlockPos().equals(target)){stop(c,"混凝土被遮挡，请调整站位");return;}
            var look=RotationAim.lookAt(c.player,aim);RotationAim.apply(c.player,look);c.hitResult=hit;
            if(!mineStarted){confirmation.beginMining();c.gameMode.startDestroyBlock(target,hit.getDirection());breaking=mineStarted=true;stateSince=ticks;}
            else c.gameMode.continueDestroyBlock(target,hit.getDirection());
            status="挖掘混凝土";
            if(ticks-stateSince>160)stop(c,"持续未能挖掉，请检查权限、网络或工具");
        }catch(Exception error){stop(c,error.getMessage()==null?error.getClass().getSimpleName():error.getMessage());}
    }
    private int selectPowder(Minecraft c){
        var inv=c.player.getInventory();int selected=inv.getSelectedSlot();if(inv.getItem(selected).is(powder)){lastSlot=selected;return selected;}
        for(int i=0;i<36;i++)if(inv.getItem(i).is(powder))return select(c,i,powderSlot);
        return -1;
    }
    private record ToolRules(String mode, List<?> items, int reserve) {}
    private ToolRules toolRules(){
        int reserve=config.concreteToolReservePercent;
        try{
            Class<?> registry=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            Object modules=registry.getMethod("get").invoke(null);
            Object tool=registry.getMethod("get",Class.class).invoke(modules,Class.forName(AUTO_TOOL));
            if(tool==null || !pausedModules.contains(AUTO_TOOL) && !(boolean)tool.getClass().getMethod("isActive").invoke(tool))return new ToolRules("None",List.of(),reserve);
            Object settings=tool.getClass().getField("settings").get(tool);
            String mode=setting(settings,"list-mode").toString();
            if((boolean)setting(settings,"anti-break"))reserve=Math.max(reserve,((Number)setting(settings,"anti-break-percentage")).intValue());
            return new ToolRules(mode,(List<?>)setting(settings,mode.equals("Whitelist")?"whitelist":"blacklist"),reserve);
        }catch(ClassNotFoundException absent){return new ToolRules("None",List.of(),reserve);}
        catch(ReflectiveOperationException e){throw new IllegalStateException("无法读取自动工具保护设置",e);}
    }
    private static Object setting(Object settings,String name)throws ReflectiveOperationException{
        Object value=settings.getClass().getMethod("get",String.class).invoke(settings,name);
        if(value==null)throw new IllegalStateException("缺少自动工具设置 "+name);
        return value.getClass().getMethod("get").invoke(value);
    }
    private int selectTool(Minecraft c,BlockState state,boolean apply){
        int best=-1;float score=-1;var inv=c.player.getInventory();var rules=toolRules();
        for(int i=0;i<36;i++){
            var s=inv.getItem(i);boolean listed=rules.items.contains(s.getItem());if(rules.mode.equals("Whitelist") && !listed || rules.mode.equals("Blacklist") && listed)continue;
            if(s.isEmpty() || !s.is(net.minecraft.tags.ItemTags.PICKAXES) || !ConcretePolicy.usableTool(s.isCorrectToolForDrops(state),s.isDamageableItem(),s.getMaxDamage(),s.getDamageValue(),rules.reserve))continue;
            float n=s.getDestroySpeed(state);if(n>score){best=i;score=n;}
        }
        return apply && best>=0?select(c,best,toolHotbar(c)):best;
    }
    private int toolHotbar(Minecraft c){
        var inv=c.player.getInventory();
        for(int i=0;i<9;i++)if(i!=powderSlot && inv.getItem(i).isEmpty())return i;
        for(int i=0;i<9;i++)if(i!=powderSlot && !inv.getItem(i).has(DataComponents.FOOD) && !inv.getItem(i).is(Items.BOW) && !inv.getItem(i).is(net.minecraft.tags.ItemTags.SWORDS))return i;
        throw new IllegalStateException("快捷栏需要一个可用于镐的位置");
    }
    private record Swap(int source,int hotbar,Item tool,Item displaced) {}
    private final List<Swap> toolSwaps=new ArrayList<>();
    private void restoreToolSlots(Minecraft c){
        if(c.player!=null && c.player.containerMenu.containerId==0 && c.gameMode!=null){
            var inv=c.player.getInventory();
            for(var swap:toolSwaps.reversed())if(inv.getItem(swap.hotbar).is(swap.tool) && (inv.getItem(swap.source).isEmpty() || inv.getItem(swap.source).is(swap.displaced)))
                c.gameMode.handleContainerInput(0,swap.source,swap.hotbar,ContainerInput.SWAP,c.player);
        }
        toolSwaps.clear();
    }
    private int select(Minecraft c,int source,int fallback){
        int slot=source;
        if(source>=9){slot=fallback;if(!c.player.getInventory().getItem(source).is(powder))toolSwaps.add(new Swap(source,slot,c.player.getInventory().getItem(source).getItem(),c.player.getInventory().getItem(slot).getItem()));c.gameMode.handleContainerInput(c.player.containerMenu.containerId,source,slot,ContainerInput.SWAP,c.player);}
        c.player.getInventory().setSelectedSlot(slot);lastSlot=slot;return slot;
    }
    /** Native sneak input avoids opening a hopper/chest used as the support. */
    private void placeSneaking(Minecraft c){
        Input previous=c.player.input!=null?c.player.input.keyPresses:Input.EMPTY;
        Input sneak=new Input(previous.forward(),previous.backward(),previous.left(),previous.right(),previous.jump(),true,previous.sprint());
        boolean key=c.options.keyShift.isDown();
        KitClient.setForceSneakForPlacement(true);c.options.keyShift.setDown(true);
        if(c.player.input!=null)c.player.input.keyPresses=sneak;
        c.player.connection.send(new ServerboundPlayerInputPacket(sneak));
        try{c.gameMode.useItemOn(c.player,InteractionHand.MAIN_HAND,placement);}
        finally{KitClient.setForceSneakForPlacement(false);c.options.keyShift.setDown(key);if(c.player.input!=null)c.player.input.keyPresses=previous;c.player.connection.send(new ServerboundPlayerInputPacket(previous));}
    }
    private void log(Minecraft c,String event){
        String line=event+" target="+target+" completed="+completed;
        KitClient.LOGGER.info("[Concrete] {}",line);
        if(c.player!=null && (event.startsWith("start")||event.startsWith("stop")))c.player.sendSystemMessage(Component.literal("[twob2tkit] 混凝土制作："+status()));
    }
}
