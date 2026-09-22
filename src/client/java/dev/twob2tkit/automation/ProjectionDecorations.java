package dev.twob2tkit.automation;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.decoration.ItemFrame;
import net.minecraft.world.entity.decoration.painting.Painting;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BannerBlockEntity;
import net.minecraft.world.level.block.entity.BannerPatternLayers;
import net.minecraft.world.phys.AABB;
import java.util.*;

/** Read-only client-visible decoration properties. Never serializes or empties container inventory. */
public final class ProjectionDecorations {
    private ProjectionDecorations(){}
    private static final Gson JSON=new Gson();
    static JsonArray patterns(BannerPatternLayers layers){
        var out=new JsonArray();
        for(var layer:layers.layers()){
            var row=new JsonObject();row.addProperty("pattern",layer.pattern().unwrapKey().map(k->k.identifier().toString()).orElse("unregistered"));
            row.addProperty("color",layer.color().getName());out.add(row);
        }
        return out;
    }
    public static JsonObject banner(BannerBlockEntity banner){
        var out=new JsonObject();var p=banner.getBlockPos();out.add("pos",JSON.toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()}));
        out.addProperty("base_color",banner.getBaseColor().getName());out.add("patterns",patterns(banner.getPatterns()));return out;
    }
    private static JsonObject item(ItemStack stack){
        var out=new JsonObject();out.addProperty("id",stack.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());out.addProperty("count",stack.getCount());
        if(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString().endsWith("_banner"))out.add("patterns",patterns(stack.getOrDefault(DataComponents.BANNER_PATTERNS,BannerPatternLayers.EMPTY)));
        return out;
    }
    public static JsonArray entities(Minecraft c,BlockPos min,BlockPos max){
        var bounds=new AABB(min.getX(),min.getY(),min.getZ(),max.getX()+1,max.getY()+1,max.getZ()+1);var out=new JsonArray();
        for(var entity:c.level.entitiesForRendering()){
            if(!entity.isAlive()||!bounds.intersects(entity.getBoundingBox()))continue;
            if(!(entity instanceof ArmorStand||entity instanceof ItemFrame||entity instanceof Painting))continue;
            var row=new JsonObject();row.addProperty("uuid",entity.getUUID().toString());row.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());
            row.add("pos",JSON.toJsonTree(new double[]{entity.getX(),entity.getY(),entity.getZ()}));row.addProperty("yaw",entity.getYRot());row.addProperty("invisible",entity.isInvisible());
            if(entity instanceof ItemFrame frame){
                row.addProperty("facing",frame.getDirection().get3DDataValue());row.addProperty("item_rotation",frame.getRotation());row.add("item",item(frame.getItem()));
            }else if(entity instanceof Painting painting){
                row.addProperty("facing",painting.getDirection().get3DDataValue());row.addProperty("variant",painting.getVariant().unwrapKey().map(k->k.identifier().toString()).orElse("unregistered"));
                row.addProperty("width",painting.getVariant().value().width());row.addProperty("height",painting.getVariant().value().height());
            }else if(entity instanceof ArmorStand stand){
                row.addProperty("small",stand.isSmall());row.addProperty("show_arms",stand.showArms());row.addProperty("base_plate",stand.showBasePlate());
                row.addProperty("default_pose",stand.getHeadPose().equals(ArmorStand.DEFAULT_HEAD_POSE)&&stand.getBodyPose().equals(ArmorStand.DEFAULT_BODY_POSE)
                    &&stand.getLeftArmPose().equals(ArmorStand.DEFAULT_LEFT_ARM_POSE)&&stand.getRightArmPose().equals(ArmorStand.DEFAULT_RIGHT_ARM_POSE)
                    &&stand.getLeftLegPose().equals(ArmorStand.DEFAULT_LEFT_LEG_POSE)&&stand.getRightLegPose().equals(ArmorStand.DEFAULT_RIGHT_LEG_POSE));
            }
            out.add(row);
        }
        return out;
    }
}
