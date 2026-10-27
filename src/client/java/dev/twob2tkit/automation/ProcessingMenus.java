package dev.twob2tkit.automation;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.inventory.*;
import net.minecraft.world.item.crafting.display.SlotDisplayContext;

/** Read current selectable options and click the same vanilla menu button as its screen. */
final class ProcessingMenus {
 static final int PROTOCOL=1;
 private ProcessingMenus(){}
 static JsonObject snapshot(Minecraft c,AbstractContainerMenu menu){
  var out=new JsonObject();var choices=new JsonArray();String kind;
  if(menu instanceof LoomMenu loom){
   kind="loom";out.addProperty("selected",loom.getSelectedBannerPatternIndex());
   var values=loom.getSelectablePatterns();
   for(int i=0;i<values.size();i++){
    var v=new JsonObject();v.addProperty("button",i);v.addProperty("key",values.get(i).unwrapKey().map(k->k.identifier().toString()).orElse("unregistered"));choices.add(v);
   }
  }else if(menu instanceof StonecutterMenu stone){
   kind="stonecutter";out.addProperty("selected",stone.getSelectedRecipeIndex());
   var context=SlotDisplayContext.fromLevel(c.level);var values=stone.getVisibleRecipes().entries();
   for(int i=0;i<values.size();i++){
    var stack=values.get(i).recipe().optionDisplay().resolveForFirstStack(context);var v=new JsonObject();
    v.addProperty("button",i);v.addProperty("key",BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());v.addProperty("count",stack.getCount());choices.add(v);
   }
  }else return out;
  out.addProperty("protocol",PROTOCOL);out.addProperty("kind",kind);out.add("options",choices);return out;
 }
 static void select(Minecraft c,JsonObject r,boolean owned,boolean manual){
  var menu=c.player.containerMenu;var info=snapshot(c,menu);
  int id=r.has("menu_id")?r.get("menu_id").getAsInt():-1,button=r.has("button")?r.get("button").getAsInt():-1;
  String kind=info.has("kind")?info.get("kind").getAsString():"",expected=r.has("expected_option")?r.get("expected_option").getAsString():"";
  var choices=info.has("options")?info.getAsJsonArray("options"):new JsonArray();
  boolean matches=button>=0&&button<choices.size()&&choices.get(button).getAsJsonObject().get("key").getAsString().equals(expected)
      &&r.has("expected_selected")&&info.get("selected").getAsInt()==r.get("expected_selected").getAsInt();
  if(!ProcessingMenuPolicy.permits(kind,owned,c.player.getHealth()>=19,manual,menu.getCarried().isEmpty(),menu.containerId,id,choices.size(),button,matches))
   throw new IllegalStateException("Processing menu, option, cursor, or material owner changed");
  int inputCount=kind.equals("loom")?3:1;
  var inputs=r.has("expected_inputs")?r.getAsJsonArray("expected_inputs"):new JsonArray();
  if(inputs.size()!=inputCount)throw new IllegalArgumentException("Exact processing input slots are required");
  for(int i=0;i<inputCount;i++){
   var expectedInput=inputs.get(i).getAsJsonObject();var actual=menu.getSlot(i).getItem();
   String item=actual.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(actual.getItem()).toString();
   if(!item.equals(expectedInput.get("item").getAsString())||actual.getCount()!=expectedInput.get("count").getAsInt())
    throw new IllegalStateException("Processing input changed; no button sent");
   if(i==0&&kind.equals("loom")){
    var patterns=ProjectionDecorations.patterns(actual.getOrDefault(net.minecraft.core.component.DataComponents.BANNER_PATTERNS,net.minecraft.world.level.block.entity.BannerPatternLayers.EMPTY));
    if(!expectedInput.has("banner_patterns")||!patterns.equals(expectedInput.getAsJsonArray("banner_patterns")))throw new IllegalStateException("Banner layers changed; no button sent");
   }
  }
  if(!menu.clickMenuButton(c.player,button))throw new IllegalStateException("Current processing menu refused this option");
  c.gameMode.handleInventoryButtonClick(menu.containerId,button);
 }
}
