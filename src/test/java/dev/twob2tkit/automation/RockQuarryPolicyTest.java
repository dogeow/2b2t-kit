package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RockQuarryPolicyTest {
    private static RockQuarryPolicy.Cell block(String name){
        boolean air=name.equals("air");
        return new RockQuarryPolicy.Cell(true,"minecraft:"+name,air,false,false,false,!air,false);
    }
    private RockQuarryPolicy.World dry(RockQuarryPolicy.Bounds b){
        return (x,y,z)->b.contains(x,y,z)||b.column(x,z)&&y==b.minY()-1?block("deepslate"):block("air");
    }
    private RockQuarryPolicy.Bounds shaft(){return new RockQuarryPolicy.Bounds(0,64,0,1,73,1);}
    @Test void shaftAndPitAreBoundedWithoutChangingUserAreaCoordinates(){
        assertTrue(RockQuarryPolicy.requestAllowed(shaft(),"minecraft:cobblestone","clear",0));
        var pit=new RockQuarryPolicy.Bounds(0,-27,0,5,-10,5);
        assertTrue(RockQuarryPolicy.requestAllowed(pit,"minecraft:cobbled_deepslate","collect",557));
        assertEquals(648,RockQuarryPolicy.inspect(dry(pit),pit,"minecraft:cobbled_deepslate").remaining());
        assertFalse(new RockQuarryPolicy.Bounds(0,0,0,1,0,1).valid(),"Equal Y would mean unbounded AREA");
        assertFalse(new RockQuarryPolicy.Bounds(0,0,0,6,17,5).valid());
        assertFalse(new RockQuarryPolicy.Bounds(0,0,0,5,18,5).valid());
        assertFalse(new RockQuarryPolicy.Bounds(3,0,0,1,17,5).valid());
        assertFalse(new RockQuarryPolicy.Bounds(Integer.MIN_VALUE,0,0,Integer.MAX_VALUE,3,3).valid());
        assertFalse(RockQuarryPolicy.requestAllowed(pit,"minecraft:sand","collect",1));
        assertFalse(RockQuarryPolicy.requestAllowed(pit,"minecraft:cobblestone","clear",1));
        assertFalse(RockQuarryPolicy.requestAllowed(pit,"minecraft:cobblestone","collect",0));
    }
    @Test void rawRockSoilAndOreAreAllowedButBuildingMaterialsArePreserved(){
        var b=shaft();
        for(String name:new String[]{"stone","deepslate","tuff","dirt","grass_block","deepslate_iron_ore","diamond_ore"}){
            var result=RockQuarryPolicy.inspect((x,y,z)->b.contains(x,y,z)?block(name):dry(b).cell(x,y,z),b,"minecraft:raw_iron");
            assertEquals(40,result.remaining());
        }
        for(String name:new String[]{"bedrock","cobblestone","cobbled_deepslate","deepslate_tiles","white_concrete",
                "oak_planks","stone_bricks","chest","sand","gravel","lantern","ladder","glass","obsidian"})
            assertThrows(IllegalStateException.class,()->RockQuarryPolicy.inspect((x,y,z)->
                b.contains(x,y,z)?block(name):dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate"),name);
    }
    @Test void ordinaryNaturalStoneVariantsHaveTheirOwnDirectDropTargets(){
        for(String name:new String[]{"andesite","diorite","granite","tuff","calcite"}){
            String id="minecraft:"+name;
            assertTrue(RockQuarryPolicy.requestAllowed(shaft(),id,"collect",1));
            assertTrue(RockQuarryPolicy.drops(id,id));
            assertFalse(RockQuarryPolicy.drops("minecraft:polished_"+name,id));
        }
    }
    @Test void deepRawIronBlockIsAnExactDropTargetRatherThanNineImaginaryRawIron(){
        var b=new RockQuarryPolicy.Bounds(0,-32,0,1,-29,1);
        String item="minecraft:raw_iron_block";
        assertTrue(RockQuarryPolicy.requestAllowed(b,item,"collect",1));
        assertTrue(RockQuarryPolicy.drops(item,item));
        assertFalse(RockQuarryPolicy.drops("minecraft:deepslate_iron_ore",item));
        assertFalse(RockQuarryPolicy.drops(item,"minecraft:raw_iron"));
        var result=RockQuarryPolicy.inspect((x,y,z)->x==0&&y==-32&&z==0?block("raw_iron_block"):
            x==1&&y==-32&&z==0?block("deepslate_iron_ore"):dry(b).cell(x,y,z),b,item);
        assertEquals(1,result.available());assertEquals(16,result.remaining());
        assertEquals(RockQuarryPolicy.Result.WAITING,RockQuarryPolicy.result("collect",1,0,0,0,false));
        assertEquals(RockQuarryPolicy.Result.DONE,RockQuarryPolicy.result("collect",1,0,1,15,true));
    }
    @Test void rawIronBlocksOutsideVanillaVeinHeightRemainProtectedForEveryQuarryTarget(){
        for(int y:new int[]{-61,-7,95}){
            var b=new RockQuarryPolicy.Bounds(0,y,0,1,y+1,1);
            for(String item:new String[]{"minecraft:raw_iron_block","minecraft:raw_iron","minecraft:tuff"})
                assertThrows(IllegalStateException.class,()->RockQuarryPolicy.inspect((x,yy,z)->
                    b.contains(x,yy,z)?block("raw_iron_block"):dry(b).cell(x,yy,z),b,item));
        }
    }
    @Test void bufferRejectsUnloadedFluidContainersAndFallingBlocksBeforeAnyExcavation(){
        var b=shaft();
        var hazards=new RockQuarryPolicy.Cell[]{
            new RockQuarryPolicy.Cell(false,"unloaded",false,false,false,false,false,false),
            new RockQuarryPolicy.Cell(true,"minecraft:water",false,true,false,false,false,false),
            new RockQuarryPolicy.Cell(true,"minecraft:lava",false,true,false,false,false,false),
            new RockQuarryPolicy.Cell(true,"minecraft:chest",false,false,true,false,true,false),
            new RockQuarryPolicy.Cell(true,"minecraft:gravel",false,false,false,true,true,false)};
        for(var hazard:hazards)assertThrows(IllegalStateException.class,()->RockQuarryPolicy.inspect((x,y,z)->
            x==-3&&y==63&&z==0?hazard:dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate"));
        assertThrows(IllegalStateException.class,()->RockQuarryPolicy.inspect((x,y,z)->
            x==0&&y==63&&z==0?block("air"):dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate"));
    }
    @Test void undergroundPitDoesNotRequireEntireCeilingToBeOpen(){
        var b=new RockQuarryPolicy.Bounds(0,-27,0,5,-10,5);
        var result=RockQuarryPolicy.inspect((x,y,z)->block("deepslate"),b,"minecraft:cobbled_deepslate");
        assertEquals(648,result.available());
    }
    @Test void retainedOrdinaryTorchesAreNotCountedAsRockOrSilentlyGeneralizedToDecorations(){
        var b=shaft();
        var result=RockQuarryPolicy.inspect((x,y,z)->b.contains(x,y,z)
            ?block(x==0?"torch":"wall_torch"):dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate");
        assertEquals(0,result.remaining());assertEquals(40,result.retainedLights());
        assertEquals(RockQuarryPolicy.Result.DONE,RockQuarryPolicy.result("clear",0,10,10,result.remaining(),true));
        assertThrows(IllegalStateException.class,()->RockQuarryPolicy.inspect((x,y,z)->
            b.contains(x,y,z)?block("soul_torch"):dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate"));
        // A previous shaft segment's wall torch in the next buffer is also retained.
        assertEquals(40,RockQuarryPolicy.inspect((x,y,z)->x==-1&&y==64&&z==0?block("wall_torch"):
            dry(b).cell(x,y,z),b,"minecraft:cobbled_deepslate").remaining());
    }
    @Test void predictedAirCannotFinishClearBeforeServerAcknowledgement(){
        var b=shaft();
        var result=RockQuarryPolicy.inspect((x,y,z)->{
            if(x==0&&y==64&&z==0)return new RockQuarryPolicy.Cell(true,"minecraft:air",true,false,false,false,false,true);
            return b.contains(x,y,z)?block("air"):dry(b).cell(x,y,z);
        },b,"minecraft:cobbled_deepslate");
        assertEquals(1,result.remaining());assertEquals(1,result.pendingBlocks());
        assertNotEquals(RockQuarryPolicy.Result.DONE,RockQuarryPolicy.result("clear",0,0,0,result.remaining(),false));
    }
    @Test void clearedAreaOrMinerStopNeverClaimsAnUncollectedInventoryTarget(){
        assertEquals(RockQuarryPolicy.Result.RUNNING,RockQuarryPolicy.result("collect",100,30,129,0,true));
        assertEquals(RockQuarryPolicy.Result.WAITING,RockQuarryPolicy.result("collect",100,30,129,0,false));
        assertEquals(RockQuarryPolicy.Result.WAITING,RockQuarryPolicy.result("collect",100,30,20,5,false));
        assertEquals(RockQuarryPolicy.Result.DONE,RockQuarryPolicy.result("collect",100,30,130,200,true));
    }
    @Test void silkAndLowDurabilityCannotConsumeAnEntirePitForZeroDesiredDrops(){
        assertTrue(RockQuarryPolicy.toolAllowed(true,1000,648,false,true));
        assertFalse(RockQuarryPolicy.toolAllowed(true,152,648,false,true));
        assertFalse(RockQuarryPolicy.toolAllowed(true,1000,648,true,true));
        assertTrue(RockQuarryPolicy.toolAllowed(true,1000,648,true,false));
        assertFalse(RockQuarryPolicy.toolAllowed(false,1000,40,false,true));
        assertTrue(RockQuarryPolicy.healthy(19,8,false));
        assertFalse(RockQuarryPolicy.healthy(18,20,false));assertFalse(RockQuarryPolicy.healthy(20,7,false));
        assertFalse(RockQuarryPolicy.healthy(20,20,true));
    }
    @Test void staleUiStopCannotCancelANewManualTaskOrAnotherWorld(){
        assertTrue(RockQuarryPolicy.ownsCancel("job","job","world","world",4,4));
        assertFalse(RockQuarryPolicy.ownsCancel("","job","world","world",4,4));
        assertFalse(RockQuarryPolicy.ownsCancel("old","job","world","world",4,4));
        assertFalse(RockQuarryPolicy.ownsCancel("job","job","old","world",4,4));
        assertFalse(RockQuarryPolicy.ownsCancel("job","job","world","world",4,5));
    }
    @Test void nativeGroundedTransitionIsAllowedButStartStillRequiresFlight(){
        assertTrue(RockQuarryPolicy.flightAllowed(true,false,true,false),"Aerial preflight");
        assertFalse(RockQuarryPolicy.flightAllowed(false,false,true,false),"Never start grounded");
        assertTrue(RockQuarryPolicy.flightAllowed(false,true,true,true),"DIG/NoFall and supported horizontal mining deliberately release Flight");
        assertTrue(RockQuarryPolicy.flightAllowed(true,true,true,true),"AREA reacquires Flight to return to top");
    }
    @Test void anotherRequestLostScopeOrStoppedForeignAreaCannotBorrowTheGroundedException(){
        assertFalse(RockQuarryPolicy.flightAllowed(false,false,true,true),"Another request is not this active rock operation");
        assertFalse(RockQuarryPolicy.flightAllowed(false,true,false,true),"Changed task/world/revision is not the material lease");
        assertFalse(RockQuarryPolicy.flightAllowed(false,true,true,false),"Stopped, manual or different-bounds AREA is not owned");
    }

}
