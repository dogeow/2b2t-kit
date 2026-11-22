package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitMapLayers;
import dev.twob2tkit.map.MapViewport;
import dev.twob2tkit.map.XaeroKitLayersOption;
import xaero.map.gui.dropdown.rightclick.GuiRightClickMenu;
import dev.twob2tkit.map.MapAreaSelection;
import dev.twob2tkit.map.XaeroCruiseOption;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.network.chat.Component;
import org.objectweb.asm.Opcodes;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import dev.twob2tkit.map.XaeroSceneryOption;
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
    @Shadow private double cameraX, cameraZ, scale, screenScale;
    @Shadow private ResourceKey<Level> mouseBlockDim;
    @Shadow private GuiRightClickMenu rightClickMenu;
    @Shadow public abstract void onRightClickClosed();

    @Unique private final KitMapLayers kit$layers = new KitMapLayers();

    @Unique private MapViewport kit$viewport(Minecraft client) {
        var window = client.getWindow();
        return new MapViewport(window.getGuiScaledWidth(), window.getGuiScaledHeight(),
            (window.getWidth()/2)/screenScale,(window.getHeight()/2)/screenScale,
            cameraX,cameraZ,scale/screenScale);
    }

    @Inject(method="mouseClicked",at=@At("HEAD"),cancellable=true,remap=false,require=0)
    private void kit$openLayerMarker(MouseButtonEvent event,boolean doubleClick,CallbackInfoReturnable<Boolean> ci) {
        if (event.button()!=0 || rightClickMenu!=null || !(scale>0 && screenScale>0)) return;
        var client=Minecraft.getInstance();
        if (kit$layers.click((Screen)(Object)this,client,mouseBlockDim,kit$viewport(client),event.x(),event.y())) ci.setReturnValue(true);
    }

    @Unique private MapAreaSelection.Point kit$areaAnchor;
    @Unique private ClientLevel kit$areaLevel;
    @Unique private double kit$pressX, kit$pressY;
    @Unique private MapAreaSelection.Point kit$draftA, kit$draftB;
    @Unique private ClientLevel kit$draftLevel;

    // This field is written only after Xaero itself accepted a right press on the map.
    @Inject(method="mouseClicked", at=@At(value="FIELD",
        target="Lxaero/map/gui/GuiMap;rightClickCoordinateScale:D",opcode=Opcodes.PUTFIELD,shift=At.Shift.AFTER),
        remap=false,require=0)
    private void kit$rememberAreaAnchor(MouseButtonEvent event, boolean doubleClick, CallbackInfoReturnable<Boolean> ci) {
        var client=Minecraft.getInstance();
        kit$areaAnchor=null;
        kit$areaLevel=null;
        if (client.player==null || client.player.isDeadOrDying() || client.level==null
                || !client.level.dimension().equals(rightClickDim) || !(scale>0 && screenScale>0)) return;
        kit$pressX=event.x();
        kit$pressY=event.y();
        kit$areaAnchor=kit$blockAt(client,event.x()*screenScale,event.y()*screenScale);
        kit$areaLevel=client.level;
    }

    @Unique private MapAreaSelection.Point kit$blockAt(Minecraft client,double x,double y) {
        return new MapAreaSelection.Point(
            MapAreaSelection.blockAt(x,client.getWindow().getWidth(),cameraX,scale),
            MapAreaSelection.blockAt(y,client.getWindow().getHeight(),cameraZ,scale));
    }

    @Inject(method="mapClicked",at=@At("HEAD"),cancellable=true,remap=false,require=0)
    private void kit$finishAreaDrag(int button,int rawX,int rawY,CallbackInfo ci) {
        if (button!=1 || kit$areaAnchor==null) return;
        var anchor=kit$areaAnchor;
        var level=kit$areaLevel;
        kit$areaAnchor=null;
        kit$areaLevel=null;
        if (!(scale>0 && screenScale>0)
                || !MapAreaSelection.dragged(kit$pressX,kit$pressY,rawX/screenScale,rawY/screenScale)) return;
        var client=Minecraft.getInstance();
        if (client.level!=level || !level.dimension().equals(mouseBlockDim) || client.player==null
                || client.player.isDeadOrDying()) return;
        var end=kit$blockAt(client,rawX,rawY);
        onRightClickClosed();
        ci.cancel();
        var border=level.getWorldBorder();
        if (!border.isWithinBounds(anchor.x()+.5,anchor.z()+.5) || !border.isWithinBounds(end.x()+.5,end.z()+.5)) {
            client.gui.hud.setOverlayMessage(Component.literal("框选区域越过世界边界"),false);
            return;
        }
        if (!MapAreaSelection.fits(anchor,end)) {
            client.gui.hud.setOverlayMessage(Component.literal("区域挖最多 "+dev.twob2tkit.borer.BorerAreaMarks.MAX_SPAN+"×"+dev.twob2tkit.borer.BorerAreaMarks.MAX_SPAN+" 格，请重新框选"),false);
            return;
        }
        kit$draftA=anchor;
        kit$draftB=end;
        kit$draftLevel=level;
    }

    @Inject(method="mouseReleased",at=@At("RETURN"),remap=false,require=0)
    private void kit$openAreaDraft(MouseButtonEvent event,CallbackInfoReturnable<Boolean> ci) {
        if (event.button()!=1 || kit$draftA==null) return;
        var a=kit$draftA;
        var b=kit$draftB;
        var level=kit$draftLevel;
        kit$draftA=kit$draftB=null;
        kit$draftLevel=null;
        var client=Minecraft.getInstance();
        Screen map=(Screen)(Object)this;
        if (client.level==level && client.gui.screen()==map) KitClient.openMapArea(client,map,a,b);
    }

    @Inject(method="extractRenderState",at=@At("TAIL"),remap=false,require=0)
    private void kit$drawAreaDrag(GuiGraphicsExtractor graphics,int x,int y,float delta,CallbackInfo ci) {
        var client=Minecraft.getInstance();
        if (rightClickMenu==null && scale>0 && screenScale>0) {
            kit$layers.render(graphics,client,mouseBlockDim,kit$viewport(client),x,y,kit$areaAnchor==null);
        }
        if (kit$areaAnchor==null || kit$areaLevel!=client.level || !kit$areaLevel.dimension().equals(mouseBlockDim)
                || !(scale>0 && screenScale>0) || !MapAreaSelection.dragged(kit$pressX,kit$pressY,x,y)) return;
        var end=kit$blockAt(client,x*screenScale,y*screenScale);
        double halfX=client.getWindow().getWidth()/2, halfZ=client.getWindow().getHeight()/2;
        int left=(int)Math.floor((halfX+(Math.min(kit$areaAnchor.x(),end.x())-cameraX)*scale)/screenScale);
        int right=(int)Math.ceil((halfX+(Math.max(kit$areaAnchor.x(),end.x())+1-cameraX)*scale)/screenScale);
        int top=(int)Math.floor((halfZ+(Math.min(kit$areaAnchor.z(),end.z())-cameraZ)*scale)/screenScale);
        int bottom=(int)Math.ceil((halfZ+(Math.max(kit$areaAnchor.z(),end.z())+1-cameraZ)*scale)/screenScale);
        boolean fits=MapAreaSelection.fits(kit$areaAnchor,end);
        int fill=fits ? 0x5544E9E0 : 0x55FF6655;
        int edge=fits ? 0xFF44E9E0 : 0xFFFF6655;
        graphics.nextStratum();
        graphics.fill(left,top,right,bottom,fill);
        graphics.fill(left,top,right,top+1,edge);
        graphics.fill(left,bottom-1,right,bottom,edge);
        graphics.fill(left,top,left+1,bottom,edge);
        graphics.fill(right-1,top,right,bottom,edge);
    }

    @Inject(method="removed",at=@At("HEAD"),remap=false,require=0)
    private void kit$forgetAreaDrag(CallbackInfo ci) {
        kit$areaAnchor=kit$draftA=kit$draftB=null;
        kit$areaLevel=kit$draftLevel=null;
    }

    @Inject(method="getRightClickOptions",at=@At("RETURN"),remap=false,require=0)
    private void kit$addCruise(CallbackInfoReturnable<ArrayList<Object>> info){
        var options=info.getReturnValue();
        if (options == null) return;
        options.add(new XaeroCruiseOption(this,options.size(),rightClickX,rightClickZ,rightClickDim));
        options.add(new XaeroSceneryOption(this,options.size(),rightClickX,rightClickZ,rightClickDim));
        var level=Minecraft.getInstance().level;
        if (level!=null) for (var action : XaeroKitLayersOption.Action.values()) {
            options.add(new XaeroKitLayersOption(this,options.size(),kit$layers,action,rightClickX,rightClickZ,
                level.dimension().equals(rightClickDim)));
        }
    }
}
