package dev.twob2tkit.runtime.engine;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerHarmlessCargoSeparationTest {
    @Test void ordinaryPickedUpMaterialsDoNotBecomeWeapons(){
        for(String item:List.of("gunpowder","rotten_flesh","bone","dirt","cobblestone","arrow"))
            assertTrue(GuardWeaponPolicy.harmlessCargo("minecraft:"+item,false,false,false,false),item);
    }
    @Test void weaponsToolsRangedItemsAndCustomCombatDataRemainUnsafe(){
        for(String item:List.of("bow","crossbow","trident","mace","iron_sword","diamond_axe",
                "diamond_shovel","netherite_spear","lava_bucket","fire_charge"))
            assertFalse(GuardWeaponPolicy.harmlessCargo("minecraft:"+item,false,false,false,false),item);
        assertFalse(GuardWeaponPolicy.harmlessCargo("custom:gunpowder",false,false,false,false));
        assertFalse(GuardWeaponPolicy.harmlessCargo(null,false,false,false,false));
        for(int bit=0;bit<4;bit++)assertFalse(GuardWeaponPolicy.harmlessCargo("minecraft:gunpowder",
            bit==0,bit==1,bit==2,bit==3));
    }
    @Test void capturedTwoLivingZombiesBelowYMinusThirteenAllowQuietWatchWithoutKillCredit(){
        boolean cargo=GuardWeaponPolicy.harmlessCargo("minecraft:gunpowder",false,false,false,false);
        double clearance=7.45-.0784*10-(-11.05);
        var threats=List.of(new BorerCombatSeparation.Threat(true,false,true,false,20.45,clearance,false,cargo),
            new BorerCombatSeparation.Threat(true,false,true,false,20.45,clearance,false,true));
        var gate=new BorerCombatSeparation();var world=new Object();var session=new BorerCombatSession<String>();
        var ids=List.of(UUID.randomUUID(),UUID.randomUUID());session.beginTick(0);
        for(UUID id:ids)session.observe(id,"still alive",true,false,true,11);
        boolean safe=BorerCombatSeparation.safe(true,true,true,false,false,threats);assertTrue(safe);
        for(int tick=0;tick<20;tick++)assertFalse(gate.observe(world,tick,safe));
        assertTrue(gate.observe(world,20,safe));session.pause(20);
        assertTrue(session.pending());assertEquals(2,session.targets().size());
        for(UUID id:ids)assertTrue(session.contains(id));
        assertFalse(BorerCombatSeparation.safe(true,true,false,false,false,threats));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,true,threats));
        assertFalse(BorerCombatSeparation.safe(true,true,true,false,false,
            List.of(new BorerCombatSeparation.Threat(true,false,true,false,11.9,clearance,false,cargo))));
    }
}
