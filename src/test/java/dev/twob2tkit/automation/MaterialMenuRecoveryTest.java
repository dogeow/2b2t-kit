package dev.twob2tkit.automation;
import java.util.*;
import net.minecraft.world.item.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialMenuRecoveryTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void ownedCursorIsRecoveredRatherThanMistakenForManualControl(){
  assertEquals(MaterialMenuRecovery.Decision.CLOSE_OWNED,MaterialMenuRecovery.decide(true,false,5,5,true));
 }
 @Test void genuineManualOrNewWorldDoesNotCloseUserMenu(){
  assertEquals(MaterialMenuRecovery.Decision.MANUAL_HANDOFF,MaterialMenuRecovery.decide(true,true,5,5,true));
  assertEquals(MaterialMenuRecovery.Decision.MANUAL_HANDOFF,MaterialMenuRecovery.decide(false,false,5,5,true));
  assertEquals(MaterialMenuRecovery.Decision.MANUAL_HANDOFF,MaterialMenuRecovery.decide(true,false,5,6,true));
 }
 @Test void fullInventoryDoesNotLeaveUnattendedPlayerInMenu(){
  assertEquals(MaterialMenuRecovery.Decision.SAFE_LOGOUT,MaterialMenuRecovery.decide(true,false,5,5,false));
 }
 @Test void accountsForCursorAndAllInputsWithoutChangingStacks(){
  var inventory=List.of(new ItemStack(Items.IRON_NUGGET,60),ItemStack.EMPTY);
  var cursor=new ItemStack(Items.IRON_NUGGET,16);
  assertTrue(MaterialMenuRecovery.fits(inventory,List.of(cursor,new ItemStack(Items.IRON_NUGGET,30))));
  assertFalse(MaterialMenuRecovery.fits(inventory,List.of(cursor,new ItemStack(Items.STONE,64))));
  assertEquals(60,inventory.getFirst().getCount());assertEquals(16,cursor.getCount());
 }
 @Test void freeSourceSlotFitsTheObservedSixteenNuggets(){
  var inventory=new ArrayList<ItemStack>();for(int i=0;i<36;i++)inventory.add(new ItemStack(Items.STONE,64));
  inventory.set(8,ItemStack.EMPTY);
  assertTrue(MaterialMenuRecovery.fits(inventory,List.of(new ItemStack(Items.IRON_NUGGET,16))));
 }
}
