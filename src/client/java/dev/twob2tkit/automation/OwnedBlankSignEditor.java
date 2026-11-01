package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractSignEditScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.SignBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import java.util.Set;

/** Opt-in completion of our own new blank sign editor through vanilla onClose, never keyboard input. */
final class OwnedBlankSignEditor {
    private record Intent(Object level,Object connection,String request,String task,long revision,
                          BlockPos target,BlockState expected,int beforeCount,long expires) {}
    private static Intent intent;
    private static int closed;
    private OwnedBlankSignEditor() {}
    static boolean policy(boolean optedIn,boolean sameOwner,boolean sameWorld,boolean sameBatch,
                          boolean backgroundIdle,boolean exactTarget,boolean exactPlacement,
                          boolean inventoryDelta,boolean emptyTransient,String[] lines,long remaining) {
        if(!optedIn||!sameOwner||!sameWorld||!sameBatch||!backgroundIdle||!exactTarget
                ||!exactPlacement||!inventoryDelta||!emptyTransient||remaining<=0||remaining>30_000
                ||lines==null||lines.length!=4)return false;
        for(String line:lines)if(!"".equals(line))return false;
        return true;
    }
    static void clear(){intent=null;}
    private static int count(Minecraft c){
        int n=0;for(int i=0;i<36;i++){var s=c.player.getInventory().getItem(i);if(s.is(Items.SPRUCE_SIGN))n+=s.getCount();}return n;
    }
    static void arm(Minecraft c,JsonObject request,Set<BlockPos> targets,long revision) {
        clear();
        if(!request.has("close_owned_blank_sign")||!request.get("close_owned_blank_sign").getAsBoolean())return;
        if(c.player==null||c.level==null||c.gui.screen()!=null||targets.size()!=1)
            throw new IllegalStateException("Blank sign editor recovery requires one owned new sign target");
        BlockPos pos=targets.iterator().next();
        Object model=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
        if(!(model instanceof BlockGetter schematic)||!c.level.getBlockState(pos).isAir()
                ||!schematic.getBlockState(pos).is(Blocks.SPRUCE_WALL_SIGN)||count(c)<1)
            throw new IllegalStateException("Blank sign editor recovery requires air and a supplied spruce wall sign goal");
        intent=new Intent(c.level,c.getConnection(),request.get("id").getAsString(),
            request.get("task_session").getAsString(),revision,pos.immutable(),schematic.getBlockState(pos),count(c),System.currentTimeMillis()+30_000);
    }
    static boolean closeIfOwned(Minecraft c,JsonObject active,long revision,boolean currentOwner,boolean currentBatch,Set<BlockPos> currentTargets) {
        Intent i=intent;if(i==null)return false;
        boolean same=active!=null&&active.has("id")&&active.has("task_session")
            &&i.request.equals(active.get("id").getAsString())&&i.task.equals(active.get("task_session").getAsString())&&i.revision==revision;
        if(!same||c.level!=i.level||c.getConnection()!=i.connection||System.currentTimeMillis()>=i.expires){clear();return false;}
        if(!(c.gui.screen() instanceof AbstractSignEditScreen screen)||c.player==null)return false;
        try {
            var signField=AbstractSignEditScreen.class.getDeclaredField("sign");signField.setAccessible(true);
            var linesField=AbstractSignEditScreen.class.getDeclaredField("messages");linesField.setAccessible(true);
            Object sign=signField.get(screen);String[] lines=(String[])linesField.get(screen);
            JsonObject proposal=ProfessionalPrinter.status().getAsJsonObject("last_proposal");
            boolean placed=proposal!=null&&proposal.has("target")&&proposal.has("final_target")&&proposal.has("hand")
                &&proposal.has("interaction_seen")&&proposal.get("interaction_seen").getAsBoolean()
                &&i.target.toShortString().equals(proposal.get("target").getAsString())
                &&i.expected.toString().equals(proposal.get("final_target").getAsString())
                &&"minecraft:spruce_sign".equals(proposal.get("hand").getAsString())
                &&c.level.getBlockState(i.target).equals(i.expected);
            boolean empty=c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty();
            for(int slot=0;slot<5;slot++)empty&=!c.player.inventoryMenu.getSlot(slot).hasItem();
            if(!policy(active.has("close_owned_blank_sign")&&active.get("close_owned_blank_sign").getAsBoolean(),
                same&&currentOwner,c.level==i.level&&c.getConnection()==i.connection,currentBatch&&currentTargets.equals(Set.of(i.target)),
                !c.isWindowActive()&&!dev.twob2tkit.KitKeys.manualMovementDown(c),
                sign instanceof SignBlockEntity entity&&entity.getBlockPos().equals(i.target),placed,
                count(c)==i.beforeCount-1,empty,lines,i.expires-System.currentTimeMillis()))return false;
            // Consume before the normal screen callback; no retry if its outcome is uncertain.
            clear();screen.onClose();closed++;return true;
        }catch(ReflectiveOperationException|RuntimeException unavailable){clear();return false;}
    }
    static JsonObject snapshot(){var out=new JsonObject();out.addProperty("armed",intent!=null);out.addProperty("closed",closed);return out;}
}
