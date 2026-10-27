package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ProcessingMenuPolicyTest {
 @Test void onlyExactHealthyOwnedMenuAndObservedOptionCanBeSelected(){
  assertTrue(ProcessingMenuPolicy.permits("loom",true,true,false,true,5,5,40,3,true));
  assertTrue(ProcessingMenuPolicy.permits("stonecutter",true,true,false,true,5,5,8,0,true));
  assertFalse(ProcessingMenuPolicy.permits("merchant",true,true,false,true,5,5,8,0,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",false,true,false,true,5,5,40,3,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",true,true,true,true,5,5,40,3,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",true,true,false,false,5,5,40,3,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",true,true,false,true,5,6,40,3,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",true,true,false,true,5,5,40,40,true));
  assertFalse(ProcessingMenuPolicy.permits("loom",true,true,false,true,5,5,40,3,false));
 }
}
