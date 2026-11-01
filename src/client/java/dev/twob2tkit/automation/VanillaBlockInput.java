package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.BlockHitResult;
/** A scoped normal client input, never a fabricated block result or packet. */
final class VanillaBlockInput {
    static final int PROTOCOL=1;
    static boolean requested(JsonObject r){
        if(!r.has("vanilla_block_input"))return false;var v=r.get("vanilla_block_input");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Vanilla block input flag must be boolean");return v.getAsBoolean();
    }
    static void perform(Minecraft c,JsonObject r,BlockPos target,Direction face,boolean owned,JsonObject observation){
        observation.addProperty("vanilla_input_handler_invoked",false);observation.addProperty("vanilla_input_handler_returned",false);
        if(!owned||c==null||c.player==null||c.level==null||c.gameMode==null||c.getCameraEntity()!=c.player
           ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<18||c.player.getAirSupply()<270
           ||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire()||c.player.hasInfiniteMaterials())throw new IllegalStateException("Normal block input needs the current healthy dry guarded owner and real player camera");
        if(!VanillaGateInputPolicy.ready(c.gameMode.isDestroying(),c.player.isHandsBusy(),c.player.isUsingItem(),c.gui.screen()!=null)
           ||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty())throw new IllegalStateException("Vanilla input is busy mining, using an item or a menu; no click sent");
        if(!(c.player.getMainHandItem().is(Items.NETHERITE_SWORD)||c.player.getMainHandItem().is(Items.DIAMOND_SWORD))
           ||!(c.player.getOffhandItem().isEmpty()||c.player.getOffhandItem().is(Items.TOTEM_OF_UNDYING)))throw new IllegalStateException("Normal gate input requires a sword and empty/totem offhand; consumptive items are excluded");
        var selected=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(model==null||!selected.key().equals(ProjectionLoadPolicy.text(r,"placement_key",8192))||!selected.contains(target)
           ||!LitematicaAccess.inVisibleLayer(target)||!LitematicaAccess.loadingReason(selected).isEmpty()||!ProjectedModelWaterGuard.loaded(c,target)
           ||!c.level.getBlockState(target).toString().equals(ProjectionLoadPolicy.text(r,"expected_state",2048))
           ||!VanillaGateInputPolicy.reachesGoal(c.level.getBlockState(target),model.getBlockState(target),c.player.getDirection()))throw new IllegalStateException("One normal gate click must reach the exact current original state");
        if(c.player.isSecondaryUseActive())throw new IllegalStateException("Secondary use is active; normal gate click not sent");
        if(c.isWindowActive()&&(dev.twob2tkit.KitKeys.isPhysicallyDown(c,c.options.keyUse)||dev.twob2tkit.KitKeys.isPhysicallyDown(c,c.options.keyAttack)))throw new IllegalStateException("Physical mouse input has control; no normal click sent");
        try{
            var pick=method("pick",float.class);var use=method("startUseItem");var delay=field("rightClickDelay");
            if(delay.getInt(c)>0)throw new IllegalStateException("Normal right-click delay is still active; no click sent");
            pick.invoke(c,1f);
            if(!(c.hitResult instanceof BlockHitResult hit)||!BlockFaceTarget.matches(hit,target,face))throw new IllegalStateException("Actual vanilla crosshair targets another block or entity; no click sent");
            // This is precisely the normal client entrypoint. It owns all hand fallback and swing semantics.
            observation.addProperty("vanilla_input_handler_invoked",true);
            use.invoke(c);
            observation.addProperty("vanilla_input_handler_returned",true);
        }catch(java.lang.reflect.InvocationTargetException e){throw new IllegalStateException("Normal client input handler failed; preserve the original request",e.getCause());}
        catch(ReflectiveOperationException e){throw new IllegalStateException("Normal client input handler unavailable; no direct-use fallback",e);}
    }
    private static java.lang.reflect.Method method(String name,Class<?>...args)throws ReflectiveOperationException{var m=Minecraft.class.getDeclaredMethod(name,args);m.setAccessible(true);return m;}
    private static java.lang.reflect.Field field(String name)throws ReflectiveOperationException{var f=Minecraft.class.getDeclaredField(name);f.setAccessible(true);return f;}
}
