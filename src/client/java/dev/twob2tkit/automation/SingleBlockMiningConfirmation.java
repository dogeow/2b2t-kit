package dev.twob2tkit.automation;

import it.unimi.dsi.fastutil.longs.Long2ObjectMap;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.multiplayer.prediction.BlockStatePredictionHandler;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/** Current-connection server evidence for AutomationBridge's ordinary single-block mine. */
public final class SingleBlockMiningConfirmation {
    public static final SingleBlockMiningConfirmation INSTANCE=new SingleBlockMiningConfirmation();
    private static final String SCOPE="single_target_server_block_update_and_native_sequence_ack";
    private final SingleBlockServerConfirmation<BlockPos,BlockState> proof=new SingleBlockServerConfirmation<>();
    private Object level,connection;
    private String world="",request="";
    private BlockPos target;
    private java.lang.reflect.Field handlerField,statesField;

    private SingleBlockMiningConfirmation() {}

    public void begin(Minecraft client,String world,String request,BlockPos target,boolean underwaterGravel) {
        if(client.level==null||client.getConnection()==null)
            throw new IllegalStateException("Single-block confirmation requires a live connection");
        prediction(client.level); // Fail before any native interaction if this game API changed.
        proof.begin(world,request,target.immutable(),state->SingleBlockRemovalPolicy.removed(
            state.isAir(),state.is(Blocks.WATER),underwaterGravel));
        this.level=client.level;this.connection=client.getConnection();
        this.world=world;this.request=request;this.target=target.immutable();
    }

    /** Uses vanilla start/continue and records only sequences that the call actually generated. */
    public boolean mine(Minecraft client,String world,String request,BlockPos target,Direction face,boolean start) {
        requireOwner(client,world,request,target);
        if(hold(client,world,request,target))return false;
        int before=prediction(client.level).currentSequence();
        try {
            return start?client.gameMode.startDestroyBlock(target,face):client.gameMode.continueDestroyBlock(target,face);
        } finally {
            int after=prediction(client.level).currentSequence();
            if(after>before)proof.sent(world,request,target,after);
            proof.clientState(world,request,target,client.level.getBlockState(target));
        }
    }

    public boolean hold(Minecraft client,String world,String request,BlockPos target) {
        if(!owns(client,world,request,target))return true;
        proof.clientState(world,request,target,client.level.getBlockState(target));
        return proof.hold(world,request,target);
    }

    public boolean confirmed(Minecraft client,String world,String request,BlockPos target) {
        return owns(client,world,request,target)&&client.level.hasChunkAt(target)
            &&proof.confirmed(world,request,target,client.level.getBlockState(target),predictionPending(client.level,target));
    }

    /** Called only at the current ClientPacketListener's block/section handler TAIL. */
    public static void serverBlock(Minecraft client,BlockPos pos,BlockState state) {
        var owned=INSTANCE;
        if(owned.ownsConnection(client)&&pos.equals(owned.target))
            owned.proof.serverBlock(owned.world,owned.request,pos,state);
    }

    /** Vanilla has applied or rejected the retained predicted state before this callback. */
    public static void serverAck(Minecraft client,int sequence) {
        var owned=INSTANCE;
        if(owned.ownsConnection(client))
            owned.proof.serverAck(owned.world,owned.request,owned.target,sequence);
    }

    public boolean serverUpdateSeen(Minecraft client,String world,String request,BlockPos target) {
        return owns(client,world,request,target)&&proof.serverUpdateSeen(world,request,target);
    }
    public String serverState(Minecraft client,String world,String request,BlockPos target) {
        if(!owns(client,world,request,target))return null;
        var state=proof.serverState(world,request,target);return state==null?null:state.toString();
    }
    public int sentSequence(String world,String request,BlockPos target) { return proof.sentSequence(world,request,target); }
    public int ackSequence(String world,String request,BlockPos target) { return proof.ackSequence(world,request,target); }
    public String scope() { return SCOPE; }

    public void close(String request,boolean confirmed) {
        proof.close(request,confirmed);
        if(this.request.equals(request)){level=connection=null;target=null;world=this.request="";}
    }

    private boolean ownsConnection(Minecraft client) {
        return target!=null&&level==client.level&&connection==client.getConnection();
    }
    private boolean owns(Minecraft client,String world,String request,BlockPos target) {
        return ownsConnection(client)&&this.world.equals(world)&&this.request.equals(request)&&this.target.equals(target);
    }
    private void requireOwner(Minecraft client,String world,String request,BlockPos target) {
        if(!owns(client,world,request,target))throw new IllegalStateException("Single-block excavation world, connection or request changed");
    }
    private BlockStatePredictionHandler prediction(ClientLevel level) {
        try {
            if(handlerField==null){
                handlerField=ClientLevel.class.getDeclaredField("blockStatePredictionHandler");
                statesField=BlockStatePredictionHandler.class.getDeclaredField("serverVerifiedStates");
                handlerField.setAccessible(true);statesField.setAccessible(true);
            }
            return (BlockStatePredictionHandler)handlerField.get(level);
        } catch(ReflectiveOperationException e) {
            throw new IllegalStateException("Cannot verify vanilla single-block prediction state",e);
        }
    }
    private boolean predictionPending(ClientLevel level,BlockPos target) {
        try{return ((Long2ObjectMap<?>)statesField.get(prediction(level))).containsKey(target.asLong());}
        catch(IllegalAccessException e){throw new IllegalStateException("Cannot read pending single-block prediction",e);}
    }
}
