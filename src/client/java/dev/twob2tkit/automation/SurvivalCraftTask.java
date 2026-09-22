package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import java.util.*;

/** Executes one explicit recipe through ordinary container packets, with no model/IPC per click. */
final class SurvivalCraftTask {
    private final int menuId, firstInventory, expectedCount, beforeCount;
    private final String output;
    private final List<Map.Entry<Integer,String>> ingredients;
    private int index, phase, cooldown, source=-1, picked;
    private String failure="";
    private boolean done;
    private final CraftConfirmation confirmation=new CraftConfirmation();

    SurvivalCraftTask(Minecraft c, JsonObject request) {
        var menu=c.player.containerMenu;
        int width=request.get("width").getAsInt();
        String type=menu.getClass().getSimpleName();
        if(width!=2 && width!=3 || !type.equals(width==2?"InventoryMenu":"CraftingMenu"))throw new IllegalStateException("Expected recipe menu is not open");
        menuId=menu.containerId;firstInventory=width==2?9:10;
        output=request.get("output").getAsString();expectedCount=request.get("produces").getAsInt();
        if(!output.matches("minecraft:[a-z0-9_]+") || expectedCount<1 || expectedCount>64)throw new IllegalArgumentException("Invalid recipe result");
        if(!menu.getCarried().isEmpty())throw new IllegalStateException("Cursor holds an item");
        for(int i=1;i<=width*width;i++)if(!menu.getSlot(i).getItem().isEmpty())throw new IllegalStateException("Crafting grid is occupied");
        ingredients=new ArrayList<>();Map<String,Integer> needed=new HashMap<>();
        for(var entry:request.getAsJsonObject("ingredients").entrySet()){
            int slot=Integer.parseInt(entry.getKey());String item=entry.getValue().getAsString();
            if(slot<1 || slot>width*width || !item.matches("minecraft:[a-z0-9_]+") || item.equals("minecraft:air"))throw new IllegalArgumentException("Invalid recipe ingredient");
            ingredients.add(Map.entry(slot,item));needed.merge(item,1,Integer::sum);
        }
        if(ingredients.isEmpty())throw new IllegalArgumentException("Recipe is empty");
        ingredients.sort(Map.Entry.comparingByKey());
        for(var entry:needed.entrySet())if(count(c,entry.getKey())<entry.getValue())throw new IllegalStateException("Missing recipe ingredient: "+entry.getKey());
        beforeCount=count(c,output);
    }
    private static String id(ItemStack stack){return stack.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();}
    private static int count(Minecraft c,String item){int count=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++){var stack=c.player.getInventory().getItem(i);if(id(stack).equals(item))count+=stack.getCount();}return count;}
    private void click(Minecraft c,int slot,int button,ContainerInput input){c.gameMode.handleContainerInput(menuId,slot,button,input,c.player);cooldown=4;confirmation.reset();}
    private static void require(boolean okay,String reason){if(!okay)throw new IllegalStateException(reason);}
    void tick(Minecraft c){
        if(done || !failure.isEmpty())return;
        try{
            require(c.player.containerMenu.containerId==menuId,"Recipe menu changed");
            if(cooldown-- >0)return;
            var menu=c.player.containerMenu;
            if(phase==4){
                boolean clear=ingredients.stream().allMatch(i->menu.getSlot(i.getKey()).getItem().isEmpty());
                if(!confirmation.ready(count(c,output)>=beforeCount+expectedCount && menu.getCarried().isEmpty() && clear,"Recipe result not confirmed in inventory"))return;
                done=true;return;
            }
            if(index==ingredients.size()){
                var result=menu.getSlot(0).getItem();
                if(!confirmation.ready(id(result).equals(output) && result.getCount()==expectedCount,"Unexpected recipe result; ingredients preserved"))return;
                click(c,0,0,ContainerInput.QUICK_MOVE);phase=4;return;
            }
            var ingredient=ingredients.get(index);int target=ingredient.getKey();String item=ingredient.getValue();
            switch(phase){
                case 0 -> {
                    require(menu.getCarried().isEmpty() && menu.getSlot(target).getItem().isEmpty(),"Recipe cursor or grid changed");
                    source=-1;
                    for(int i=firstInventory;i<firstInventory+36;i++)if(id(menu.getSlot(i).getItem()).equals(item)){source=i;break;}
                    require(source>=0,"Recipe ingredient moved or disappeared");picked=menu.getSlot(source).getItem().getCount();
                    click(c,source,0,ContainerInput.PICKUP);phase=1;
                }
                case 1 -> {
                    if(!confirmation.ready(id(menu.getCarried()).equals(item) && menu.getCarried().getCount()==picked && menu.getSlot(source).getItem().isEmpty(),"Recipe pickup was not confirmed"))return;
                    click(c,target,1,ContainerInput.PICKUP);phase=2;
                }
                case 2 -> {
                    if(!confirmation.ready(id(menu.getSlot(target).getItem()).equals(item) && menu.getSlot(target).getItem().getCount()==1 && menu.getCarried().getCount()==picked-1 && (picked==1||id(menu.getCarried()).equals(item)),"Recipe distribution changed"))return;
                    if(picked>1){click(c,source,0,ContainerInput.PICKUP);phase=3;}
                    else{index++;phase=0;}
                }
                case 3 -> {
                    if(!confirmation.ready(menu.getCarried().isEmpty() && id(menu.getSlot(source).getItem()).equals(item) && menu.getSlot(source).getItem().getCount()==picked-1,"Recipe remainder not returned"))return;
                    index++;phase=0;
                }
                default -> throw new IllegalStateException("Unknown recipe phase");
            }
        }catch(Exception e){failure=e.getMessage();}
    }
    boolean done(){return done;}
    String failure(){return failure;}
    JsonObject progress(){JsonObject j=new JsonObject();j.addProperty("kind","craft_recipe");j.addProperty("output",output);j.addProperty("ingredients_done",index);j.addProperty("ingredients_total",ingredients.size());j.addProperty("done",done);j.addProperty("failure",failure);return j;}
}
