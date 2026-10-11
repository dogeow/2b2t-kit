package dev.twob2tkit.mixin;

import dev.twob2tkit.map.XaeroCruiseOption;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import java.util.ArrayList;

@Pseudo
@Mixin(targets="xaero.map.gui.GuiMap",remap=false)
public abstract class XaeroMapCruiseMenuMixin {
    @Shadow private int rightClickX;
    @Shadow private int rightClickZ;
    @Shadow private ResourceKey<Level> rightClickDim;
    @Inject(method="getRightClickOptions",at=@At("RETURN"),remap=false,require=0)
    private void kit$addCruise(CallbackInfoReturnable<ArrayList<Object>> info){
        var options=info.getReturnValue();
        if(options!=null)options.add(new XaeroCruiseOption(this,options.size(),rightClickX,rightClickZ,rightClickDim));
    }
}
