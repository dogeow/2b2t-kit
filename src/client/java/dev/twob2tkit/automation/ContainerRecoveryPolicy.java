package dev.twob2tkit.automation;
import java.util.Set;

/** Explicit shulker retrieval is separate from general block mining. */
public final class ContainerRecoveryPolicy {
    private static final Set<String> COLORS=Set.of("white","orange","magenta","light_blue","yellow","lime","pink","gray","light_gray","cyan","purple","blue","brown","green","red","black");
    private ContainerRecoveryPolicy() {}
    public static boolean allowed(String id,boolean explicit,int freeSlots){
        if(!explicit || freeSlots<1 || id==null)return false;
        if(id.equals("minecraft:shulker_box"))return true;
        return COLORS.stream().anyMatch(c->id.equals("minecraft:"+c+"_shulker_box"));
    }
}
