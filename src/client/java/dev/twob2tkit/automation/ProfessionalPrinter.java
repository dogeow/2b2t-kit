package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.MeteorModules;
import net.minecraft.client.Minecraft;

/** Delegate placement to the installed Litematica Printer, never to two placers. */
public final class ProfessionalPrinter {
    private static final String CONFIG="me.aleksilassila.litematica.printer.config.Configs";
    private static final String AIR="meteordevelopment.meteorclient.systems.modules.world.AirPlace";
    private static boolean owned, paused,placementSneak,recheck;
    private static net.minecraft.world.item.Item expectedHand;
    private static long lastOwnedClick;
    private static int recoveredMenus;
    public static boolean requiresSneak(){return owned&&!paused&&placementSneak&&failure.isEmpty();}
    public static boolean consumeRecheck(){boolean value=recheck;recheck=false;return value;}
    public static boolean prepareInteraction(net.minecraft.client.player.LocalPlayer player,net.minecraft.world.InteractionHand hand,net.minecraft.world.phys.BlockHitResult hit){
        var c=Minecraft.getInstance();
        if(!owned||paused||pendingAnchor==null||!hit.getBlockPos().equals(pendingAnchor)||hit.getDirection()!=pendingFace)return false;
        if(c.isWindowActive()&&dev.twob2tkit.KitKeys.isPhysicallyDown(c,c.options.keyUse))return false;
        if(expectedHand!=null&&expectedHand!=net.minecraft.world.item.Items.AIR&&!player.getItemInHand(hand).is(expectedHand)){
            lastHandMismatch="expected="+expectedHand+" actual="+player.getItemInHand(hand).getItem();recheck=true;paused=true;return true; // An exhausted/swapped stack must never become an empty-hand container click.
        }
        if(placementSneak){
            var i=player.input.keyPresses;
            player.input.keyPresses=new net.minecraft.world.entity.player.Input(i.forward(),i.backward(),i.left(),i.right(),i.jump(),true,i.sprint());
            player.connection.send(new net.minecraft.network.protocol.game.ServerboundPlayerInputPacket(player.input.keyPresses));
        }
        lastOwnedClick=System.currentTimeMillis();return false;
    }
    public static boolean recoverOwnedContainer(Minecraft c){
        if(!owned||c.player==null||!(c.screen instanceof net.minecraft.client.gui.screens.inventory.AbstractContainerScreen<?>)||c.player.containerMenu.containerId==0||!c.player.containerMenu.getCarried().isEmpty()||lastOwnedClick==0||System.currentTimeMillis()-lastOwnedClick>1500)return false;
        lastOwnedClick=0;c.player.closeContainer();recheck=true;
        if(++recoveredMenus>1)fail(c,"打印器反复打开容器，已停止并保留现场");
        dev.twob2tkit.KitClient.LOGGER.info("[Build] closed-owned-container and requested inventory rescan");return true;
    }
    public static boolean owned(){return owned;}
    public static void resume(){paused=false;}
    private static int elapsedTicks;
    private static int savedInterval=-1,lastWrittenInterval=40;
    private static boolean fastEnabled=true;
    private static ConfirmedPlacementPacer pacing=new ConfirmedPlacementPacer();
    private static PlacementTravelBarrier<net.minecraft.core.BlockPos,net.minecraft.world.level.block.state.BlockState> travel=new PlacementTravelBarrier<>(PrinterStateConfirmation::matches);
    /** Used only to finish a station early. It does not alter native placement pacing. */
    public static boolean readyForTravel(){return travel.settled()&&queueIdleForTravel();}
    public static boolean queueIdleForTravel(){
        if(!owned||paused||!failure.isEmpty()||pacing.awaiting())return false;
        try{
            Object p=Class.forName("me.aleksilassila.litematica.printer.LitematicaMixinMod").getField("printer").get(null);
            return p!=null && queue(p).isEmpty() && (boolean)handler(p).getClass().getMethod("acceptsActions").invoke(handler(p));
        }catch(ReflectiveOperationException|RuntimeException unavailable){return false;}
    }
    private static net.minecraft.core.BlockPos candidateTarget,pendingTarget,pendingAnchor;
    private static net.minecraft.world.level.block.state.BlockState candidateState;
    private static final JsonObject lastProposal=new JsonObject();
    private static String lastHandMismatch="";
    public static void prepareActualTool(Object action,Minecraft c,net.minecraft.client.player.LocalPlayer player){
        if(!owned||paused||c.screen!=null||c.player!=player||player.containerMenu!=player.inventoryMenu||!player.containerMenu.getCarried().isEmpty()||player.isUsingItem())return;
        try{
            Object raw=action.getClass().getField("context").get(action);
            if(!(raw instanceof net.minecraft.world.item.context.BlockPlaceContext context))return;
            var desired=context.getItemInHand();
            if(!desired.isDamageableItem()||desired.getItem() instanceof net.minecraft.world.item.BlockItem||player.getMainHandItem().is(desired.getItem()))return;
            var inventory=player.getInventory();
            for(int slot=0;slot<36;slot++){
                var real=inventory.getItem(slot);
                if(!real.is(desired.getItem())||real.isEmpty()||real.isDamageableItem()&&real.getMaxDamage()-real.getDamageValue()<2)continue;
                int selected=slot<9?slot:inventory.getSelectedSlot();
                if(slot>=9)c.gameMode.handleContainerInput(0,slot,selected,net.minecraft.world.inventory.ContainerInput.SWAP,player);
                inventory.setSelectedSlot(selected);lastProposal.addProperty("actual_tool_selected",real.getItem().toString());return;
            }
        }catch(ReflectiveOperationException e){fail(c,"无法核对打印器工具准备");}
    }
    public static void observeCandidate(Object source){
        try{candidateTarget=((net.minecraft.core.BlockPos)source.getClass().getField("blockPos").get(source)).immutable();candidateState=(net.minecraft.world.level.block.state.BlockState)source.getClass().getField("targetState").get(source);}
        catch(ReflectiveOperationException e){fail(Minecraft.getInstance(),"无法读取打印器的原始目标");}
    }
    private static net.minecraft.core.Direction pendingFace;
    private static net.minecraft.world.level.block.state.BlockState pendingState,pendingFinalState;
    private static String failure="";
    private static int fastProposals,complexProposals,confirmedPlacements;
    private static long sessionNanos;
    private static final java.util.List<Double> confirmationSeconds=new java.util.ArrayList<>();
    public static String failure(){return failure;}
    public static void clearFailure(){failure="";recoveredMenus=0;}
    private static Object handler(Object printer)throws ReflectiveOperationException{return printer.getClass().getField("actionHandler").get(printer);}
    private static java.util.Queue<?> queue(Object printer)throws ReflectiveOperationException{
        Object h=handler(printer);var f=h.getClass().getDeclaredField("actionQueue");f.setAccessible(true);return (java.util.Queue<?>)f.get(h);
    }
    public static boolean allowNativeProposal(Object printer){
        if(AutomationBridge.ownsMaterialInventory()&&!owned)return false;
        if(!owned)return true;
        var c=Minecraft.getInstance();
        candidateTarget=null;candidateState=null;
        try{return pacing.acquire(elapsedTicks,paused||c.screen!=null||AutomationBridge.guardBusy()||!failure.isEmpty(),(boolean)handler(printer).getClass().getMethod("acceptsActions").invoke(handler(printer)));}
        catch(ReflectiveOperationException e){fail(c,"无法检查打印队列，已停止放置");return false;}
    }
    public static void nativeProposalQueued(Object printer){
        if(!owned)return;
        var c=Minecraft.getInstance();
        try{
            if(queue(printer).isEmpty()){pacing.cancelUnsent(elapsedTicks);return;}
            Object h=handler(printer),prepare=h.getClass().getField("lookAction").get(h);
            pendingTarget=pendingAnchor=null;pendingState=null;pendingFace=null;placementSneak=false;expectedHand=null;
            boolean simple=false;
            if(prepare!=null&&queue(printer).contains(prepare)){
                Object raw=prepare.getClass().getField("context").get(prepare);
                if(raw instanceof net.minecraft.world.item.context.BlockPlaceContext context){
                    placementSneak=raw.getClass().getField("shouldSneak").getBoolean(raw);expectedHand=context.getItemInHand().getItem();
                    var target=candidateTarget;var world=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
                    if(world!=null&&target!=null&&candidateState!=null){
                        var selection=dev.twob2tkit.builder.LitematicaAccess.buildSelection();
                        if(!selection.contains(target)||!dev.twob2tkit.builder.LitematicaAccess.inVisibleLayer(target))throw new IllegalStateException("Printer proposed a target outside the selected projection");
                        pendingFinalState=candidateState;
                        var state=candidateState;
                        boolean placement=context.getItemInHand().getItem() instanceof net.minecraft.world.item.BlockItem && context.getClickedPos().equals(target);
                        if(placement){var predicted=((net.minecraft.world.item.BlockItem)context.getItemInHand().getItem()).getBlock().getStateForPlacement(context);state=PrinterStateConfirmation.placementExpectation(candidateState,predicted);}
                        simple=context.getItemInHand().getItem() instanceof net.minecraft.world.item.BlockItem && ConfirmedPlacementPacer.safeSimple(state.getProperties().isEmpty(),state.isCollisionShapeFullBlock(world,target),state.getBlock() instanceof net.minecraft.world.level.block.FallingBlock,state.getBlock() instanceof net.minecraft.world.level.block.EntityBlock);
                        var hit=(net.minecraft.world.phys.BlockHitResult)raw.getClass().getField("hitResult").get(raw);
                        pendingTarget=target;pendingState=state;pendingAnchor=hit.getBlockPos().immutable();pendingFace=hit.getDirection();
                    }
                }
            }
            if(pendingTarget==null||pendingState==null)throw new IllegalStateException("Printer action has no verified target");
            lastProposal.addProperty("target",pendingTarget.toShortString());lastProposal.addProperty("expected",pendingState.toString());lastProposal.addProperty("final_target",pendingFinalState.toString());
            lastProposal.addProperty("hand",String.valueOf(expectedHand));lastProposal.addProperty("anchor",pendingAnchor==null?"":pendingAnchor.toShortString());
            travel.queued(pendingTarget,pendingState);
            pacing.queued(elapsedTicks,simple);setInterval(simple&&fastEnabled?2:4);
            if(simple&&fastEnabled)fastProposals++;else complexProposals++;
        }catch(ReflectiveOperationException|RuntimeException e){fail(c,"打印器接口不兼容，已停止放置");}
    }
    public static void noteInteraction(net.minecraft.client.player.LocalPlayer player,net.minecraft.world.InteractionHand hand,net.minecraft.world.phys.BlockHitResult hit){
        if(!owned||pendingTarget==null||pendingState==null||paused)return;
        if(hit.getBlockPos().equals(pendingAnchor)&&hit.getDirection()==pendingFace&&(expectedHand==null||expectedHand==net.minecraft.world.item.Items.AIR||player.getItemInHand(hand).is(expectedHand))){travel.sent(pendingTarget);pacing.sent(elapsedTicks);}
    }
    public static void serverBlock(net.minecraft.core.BlockPos pos,net.minecraft.world.level.block.state.BlockState state){
        if(!owned)return;
        if(pendingTarget==null||!pos.equals(pendingTarget)||!pacing.sent())return;
        boolean finalMatch=pendingFinalState!=null&&PrinterStateConfirmation.matches(pendingFinalState,state);
        if(PrinterStateConfirmation.matches(pendingState,state)||finalMatch){
            travel.acknowledge(pos);lastProposal.addProperty("ack_actual",state.toString());lastProposal.addProperty("ack_final",finalMatch);
            if(pacing.acknowledge()){confirmedPlacements++;if(confirmationSeconds.size()<64)confirmationSeconds.add((System.nanoTime()-sessionNanos)/1e9);}
        }else if(!state.isAir()&&!state.canBeReplaced())fail(Minecraft.getInstance(),"服务器返回的方块与当前放置动作不一致，已停止放置");
    }
    private static void setInterval(int value)throws ReflectiveOperationException{
        Object i=option("PRINTING_INTERVAL");int current=(int)i.getClass().getMethod("getIntegerValue").invoke(i);
        if(current!=lastWrittenInterval)throw new IllegalStateException("打印器间隔已由外部修改");
        if(current!=value)i.getClass().getMethod("setIntegerValue",int.class).invoke(i,value);
        lastWrittenInterval=value;
    }
    private static void fail(Minecraft c,String reason){
        failure=reason;paused=true;
        try{set("PRINT_MODE",false);Object p=Class.forName("me.aleksilassila.litematica.printer.LitematicaMixinMod").getField("printer").get(null);if(p!=null)queue(p).clear();}
        catch(ReflectiveOperationException ignored){}
        // Do not null the native singleton inside its onGameTick callback; the owner stops at its next tick.
    }

    private ProfessionalPrinter() {}
    private static Object option(String name)throws ReflectiveOperationException {
        return Class.forName(CONFIG).getField(name).get(null);
    }
    private static boolean get(String name)throws ReflectiveOperationException {
        Object o=option(name);return (boolean)o.getClass().getMethod("getBooleanValue").invoke(o);
    }
    private static void set(String name,boolean value)throws ReflectiveOperationException {
        Object o=option(name);o.getClass().getMethod("setBooleanValue",boolean.class).invoke(o,value);
    }
    public static JsonObject status(){
        JsonObject j=new JsonObject();
        try{j.addProperty("available",true);j.addProperty("enabled",get("PRINT_MODE"));j.addProperty("rotate",get("ROTATE"));j.addProperty("in_air",get("PRINT_IN_AIR"));Object i=option("PRINTING_INTERVAL");j.addProperty("interval",(int)i.getClass().getMethod("getIntegerValue").invoke(i));}
        catch(ReflectiveOperationException e){j.addProperty("available",false);j.addProperty("error",e.toString());}
        j.add("last_proposal",lastProposal.deepCopy());j.addProperty("last_hand_mismatch",lastHandMismatch);j.addProperty("action_interval_unit","client_ticks");j.addProperty("owned_menu_recoveries",recoveredMenus);j.addProperty("placement_sneak",placementSneak);j.addProperty("air_place",MeteorModules.isActive(AIR));j.addProperty("owned",owned);j.addProperty("proposal_period_ticks",fastEnabled?8:20);j.addProperty("fast_proposals",fastProposals);j.addProperty("complex_proposals",complexProposals);j.addProperty("server_confirmed",confirmedPlacements);j.addProperty("waiting_for_server",owned&&pacing.awaiting());j.addProperty("travel_pending",travel.pendingCount());j.addProperty("ready_for_travel",owned&&readyForTravel());j.addProperty("failure",failure);j.add("confirmation_seconds",new com.google.gson.Gson().toJsonTree(confirmationSeconds));return j;
    }
    public static void start(){start(true);}
    public static void start(boolean acceleratePlainBlocks){
        try{
            if(!PrinterGateInstalled.class.isAssignableFrom(Class.forName("me.aleksilassila.litematica.printer.Printer")))throw new IllegalStateException("Native printer safety gate is not installed");
            if(!PrinterCandidateGateInstalled.class.isAssignableFrom(Class.forName("me.aleksilassila.litematica.printer.guides.Guides")))throw new IllegalStateException("Native printer target observer is not installed");
            Class.forName("me.aleksilassila.litematica.printer.ActionHandler").getDeclaredField("actionQueue");
            if(!get("ROTATE"))throw new IllegalStateException("Enable printer rotation before automation");
            if(get("PRINT_IN_AIR"))throw new IllegalStateException("Disable in-air printing before automation");
            if(MeteorModules.isActive(AIR))throw new IllegalStateException("Disable Meteor Air Place before printer automation");
            Object interval=option("PRINTING_INTERVAL");
            int old=(int)interval.getClass().getMethod("getIntegerValue").invoke(interval);
            if(old<1)throw new IllegalStateException("Invalid printer action tick interval");
            placementSneak=false;recheck=false;lastOwnedClick=0;expectedHand=null;savedInterval=old;lastWrittenInterval=4;interval.getClass().getMethod("setIntegerValue",int.class).invoke(interval,4);
            set("PRINT_MODE",false);elapsedTicks=0;owned=true;paused=false;fastEnabled=acceleratePlainBlocks;pacing=new ConfirmedPlacementPacer(fastEnabled);travel=new PlacementTravelBarrier<>(PrinterStateConfirmation::matches);sessionNanos=System.nanoTime();confirmationSeconds.clear();pendingTarget=pendingAnchor=null;pendingState=null;failure="";fastProposals=complexProposals=confirmedPlacements=0;
        }catch(ReflectiveOperationException e){throw new IllegalStateException("Installed Litematica Printer is not compatible",e);}
    }
    public static void tick(Minecraft c){
        if(!owned)return;
        if(!failure.isEmpty()){stop(c,true);return;}
        try{
            boolean canWork=c.screen==null&&!paused&&!AutomationBridge.guardBusy();
            if(canWork&&pacing.timedOut(elapsedTicks)){fail(c,"服务器未确认上一格，已停止放置；请检查网络或权限");return;}
            set("PRINT_MODE",canWork&&failure.isEmpty());
            if(canWork)elapsedTicks++;
        }catch(ReflectiveOperationException e){fail(c,"打印器节奏控制失败，已停止放置");}
    }
    /** Drop queued proposals before combat, retaining the placement session and its interval lease. */
    public static void pause(){
        if(!owned)return;
        paused=true;travel.cancelUnsent();
        if(pacing.cancelUnsent(elapsedTicks)){pendingTarget=pendingAnchor=null;pendingState=null;}
        try{set("PRINT_MODE",false);Class.forName("me.aleksilassila.litematica.printer.LitematicaMixinMod").getField("printer").set(null,null);}
        catch(ReflectiveOperationException e){throw new IllegalStateException("Could not pause printer",e);}
    }
    /** Disable the mode and discard its pending placement/rotation queue before moving. */
    public static void stop(Minecraft c,boolean force){
        if(!owned && !force)return;
        try{
            boolean wasEnabled=get("PRINT_MODE");set("PRINT_MODE",false);
            Class.forName("me.aleksilassila.litematica.printer.LitematicaMixinMod").getField("printer").set(null,null);
            if((wasEnabled||owned) && c.options!=null)c.options.keyShift.setDown(false);
            if(savedInterval>=0){Object i=option("PRINTING_INTERVAL");if((int)i.getClass().getMethod("getIntegerValue").invoke(i)==lastWrittenInterval)i.getClass().getMethod("setIntegerValue",int.class).invoke(i,savedInterval);}
        }catch(ClassNotFoundException absent){/* Optional dependency. */}
        catch(ReflectiveOperationException e){throw new IllegalStateException("Could not stop Litematica Printer",e);}
        finally{owned=false;paused=false;placementSneak=false;expectedHand=null;lastOwnedClick=0;recheck=false;savedInterval=-1;pendingTarget=pendingAnchor=null;pendingState=null;}
    }
}
