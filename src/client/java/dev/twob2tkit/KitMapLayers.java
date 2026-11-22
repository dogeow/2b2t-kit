package dev.twob2tkit;

import dev.twob2tkit.automation.ProjectionAudit;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.builder.LitematicaAccess.BuildSelection;
import dev.twob2tkit.combat.ServerDeathSync;
import dev.twob2tkit.map.MapLayerDrawing;
import dev.twob2tkit.map.MapViewport;
import dev.twob2tkit.runtime.api.MapTaskView;
import dev.twob2tkit.runtime.api.MapTaskView.Area;
import dev.twob2tkit.storage.StorageDetailScreen;
import dev.twob2tkit.storage.StorageLabels;
import dev.twob2tkit.storage.StorageLifecycle;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/** View state owned by one Xaero map screen. Game actions still use the existing Kit entry points. */
public final class KitMapLayers {
    enum Layer {
        SCENERY("预加载覆盖"), ROUTES("返程与巡航"), STORAGE("仓库与物资"),
        PLACES("地点和死亡点"), PROJECTION("投影施工");
        final String title;
        Layer(String title) { this.title = title; }
    }

    private static final int SCENERY = 0xFF4EDAC4, ROUTE = 0xFFF3CA57, NEXT = 0xFF6CD3FF;
    private static final int PLACE = 0xFFC4A0FF, DEATH = 0xFFFF7777, STORAGE = 0xFFFFCE81;
    private static final int PROJECTION = 0xFF8EB2FF, MISSING = 0xA0FF8A58;
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("MM-dd HH:mm:ss").withZone(ZoneId.systemDefault());

    private final EnumSet<Layer> enabled = visibleLayers(KitClient.config() == null ? null : KitClient.config().hiddenMapLayers);
    private String query = "";
    private ClientLevel level;
    private long refreshAt;
    private List<Pin> pins = List.of(), visiblePins = List.of();
    private MapTaskView.Route mineRoute;
    private BuildSelection projection;
    private String projectionStatus = "";
    private ProjectionCheck projectionCheck;
    private MapTaskView.Scenery scenery, preview;
    private Area lastViewport;
    private ResourceKey<Level> markerDimension;

    private record Pin(double x, double z, int color, String title, List<String> detail,
                       KitConfig.StorageSnapshot storage, BlockPos guide) {}
    private record ProjectionCheck(String key, long time, Map<Long, Integer> missing) {}

    public void render(GuiGraphicsExtractor g, Minecraft c, ResourceKey<Level> dimension,
                       MapViewport view, int mouseX, int mouseY, boolean allowHover) {
        var config = KitClient.config();
        if (c.level == null || c.player == null || dimension == null || config == null) {
            visiblePins = List.of();
            return;
        }
        boolean currentDimension = dimension.equals(c.level.dimension());
        if (level != c.level) {
            level = c.level;
            query = "";
            projectionCheck = null;
            preview = null;
            lastViewport = null;
            refreshAt = 0;
        }
        long now = System.nanoTime();
        boolean refresh = now >= refreshAt;
        if (refresh) {
            refreshAt = now + 350_000_000;
            refresh(c, config);
        }
        g.nextStratum();
        var draw = new MapLayerDrawing(g, view);
        if (currentDimension && enabled.contains(Layer.SCENERY) && KitClient.borer() != null) {
            Area viewport = view.bounds();
            if (refresh || !viewport.equals(lastViewport)) {
                scenery = KitClient.borer().mapScenery(c, viewport);
                lastViewport = viewport;
            }
            if (scenery != null) {
                drawScenery(draw, c, scenery);
                if (KitClient.borer().isSceneryActive()) preview = null;
                else if (preview != null) drawSceneryTarget(draw,c,preview);
            }
        }
        if (currentDimension && enabled.contains(Layer.ROUTES)) drawRoutes(draw, c);
        if (currentDimension && enabled.contains(Layer.PROJECTION)) drawProjection(draw, g, c, view);

        var markers = new ArrayList<Pin>();
        if (currentDimension && enabled.contains(Layer.STORAGE)) markers.addAll(pins);
        if (enabled.contains(Layer.PLACES)) markers.addAll(placePins(c, config, dimension.identifier().toString()));
        visiblePins = List.copyOf(markers);
        markerDimension = dimension;
        Pin hover = allowHover ? nearest(view, mouseX, mouseY) : null;
        for (Pin pin : visiblePins) {
            int x = (int)Math.round(view.x(pin.x)), y = (int)Math.round(view.z(pin.z));
            if (!view.visible(x,y,6)) continue;
            int size = pin == hover ? 5 : 3;
            g.fill(x-size-1,y-size-1,x+size+2,y+size+2,0xE0182230);
            g.fill(x-size,y-size,x+size+1,y+size+1,pin.color);
        }
        if (hover != null) {
            var tooltip = new ArrayList<String>();
            tooltip.add(hover.title);
            tooltip.addAll(hover.detail);
            tooltip.add("点击查看详情");
            label(g, c, view, mouseX + 10, mouseY + 11, tooltip);
        } else if (currentDimension && enabled.contains(Layer.STORAGE) && !query.isBlank()) {
            label(g, c, view, 8, view.height()-47, List.of("物资「"+query+"」 · "+pins.size()+" 处有记录"));
        }
    }

    private void refresh(Minecraft c, KitConfig config) {
        if (enabled.contains(Layer.STORAGE)) {
            pins = config.storageSnapshots.stream().filter(s -> StorageLifecycle.canGuide(c, s))
                .filter(s -> query.isBlank() || matchesQuery(KitRecordPages.storageSearch(s), query))
                .map(s -> new Pin(s.x+.5, s.z+.5, STORAGE, StorageLabels.headline(s),
                    List.of(coordinates(s.x,s.y,s.z,s.dimension), StorageLabels.evidenceSummary(s),
                        StorageLabels.quantitySummary(s, query)), s, null)).toList();
        }
        mineRoute = enabled.contains(Layer.ROUTES) && KitClient.borer() != null ? KitClient.borer().mapReturnRoute(c) : null;
        if (enabled.contains(Layer.PROJECTION)) refreshProjection();
    }

    static boolean matchesQuery(String searchable, String query) {
        String text = searchable.toLowerCase(Locale.ROOT);
        for (String word : query.strip().toLowerCase(Locale.ROOT).split("\\s+")) {
            if (!text.contains(word)) return false;
        }
        return true;
    }

    private void refreshProjection() {
        try {
            projection = LitematicaAccess.buildSelection();
            projectionStatus = LitematicaAccess.loadingReason(projection);
            if (projectionCheck != null && !projection.key().equals(projectionCheck.key)) projectionCheck = null;
        } catch (IllegalStateException unavailable) {
            projection = null;
            projectionStatus = unavailable.getMessage();
            projectionCheck = null;
        }
    }

    private static void drawScenery(MapLayerDrawing draw, Minecraft c, MapTaskView.Scenery info) {
        for (Area area : info.missing()) draw.area(area, 0x58FC8D58, 0);
        draw.circle(info.x(), info.z(), info.radius(), SCENERY);
        drawSceneryTarget(draw,c,info);
    }

    private static void drawSceneryTarget(MapLayerDrawing draw, Minecraft c, MapTaskView.Scenery info) {
        if (info.batch() != null) draw.area(info.batch(), 0x2451CFFF, NEXT);
        if (info.next() != null) {
            draw.line(c.player.getX(), c.player.getZ(), info.next().getX(), info.next().getZ(), SCENERY);
        }
    }

    private void drawRoutes(MapLayerDrawing draw, Minecraft c) {
        if (mineRoute != null) {
            for (var segment : mineRoute.recorded()) draw.polyline(segment, ROUTE);
            var next = mineRoute.next().stream().map(Vec3::atBottomCenterOf).toList();
            drawPath(draw, c.player.position(), next, NEXT);
        }
        var controller = KitClient.controller();
        var conf = KitClient.config();
        if (controller != null && controller.isActive() && conf.hasTarget) {
            Vec3 here = c.player.position();
            draw.line(here.x, here.z, conf.targetX, conf.targetZ, 0x90F3CA57);
            drawPath(draw, here, controller.mapNext(c), NEXT);
        }
    }

    private static void drawPath(MapLayerDrawing draw, Vec3 from, List<Vec3> points, int color) {
        for (Vec3 next : points) {
            draw.line(from.x,from.z,next.x,next.z,color);
            from = next;
        }
    }

    private void drawProjection(MapLayerDrawing draw, GuiGraphicsExtractor g, Minecraft c, MapViewport view) {
        if (projection == null) return;
        for (var box : projection.boxes()) {
            draw.area(new Area(box.min().getX(), box.min().getZ(), box.max().getX()+1, box.max().getZ()+1), 0x257FAAFF, PROJECTION);
        }
        if (projectionCheck != null) for (var entry : projectionCheck.missing.entrySet()) {
            int x = (int)(entry.getKey() >> 32), z = (int)(long)entry.getKey();
            int alpha = Math.min(0xDF, 0x40 + entry.getValue() * 14);
            draw.area(new Area(x,z,x+4,z+4), (MISSING & 0xFFFFFF) | alpha << 24, 0);
        }
        BlockPos origin = projection.origin();
        double x = view.x(origin.getX()+.5), y = view.z(origin.getZ()+.5);
        if (view.visible(x,y,0)) {
            double bearing = projectionBearing(projection.rotation());
            double dx = -Math.sin(bearing), dz = Math.cos(bearing);
            double length = Math.min(64, 20 / view.pixelsPerBlock());
            draw.line(origin.getX()+.5,origin.getZ()+.5,origin.getX()+.5+dx*length,origin.getZ()+.5+dz*length,PROJECTION);
            label(g,c,view,(int)x+6,(int)y+5,List.of(projection.name()+" · "+rotationLabel(projection.rotation())));
        }
    }

    static double projectionBearing(String rotation) {
        return switch (rotation) {
            case "CLOCKWISE_90" -> Math.PI / 2;
            case "CLOCKWISE_180" -> Math.PI;
            case "COUNTERCLOCKWISE_90" -> -Math.PI / 2;
            default -> 0;
        };
    }

    private static String rotationLabel(String rotation) {
        return switch (rotation) {
            case "CLOCKWISE_90" -> "顺时针 90°";
            case "CLOCKWISE_180" -> "180°";
            case "COUNTERCLOCKWISE_90" -> "逆时针 90°";
            default -> "0°";
        };
    }

    private static List<Pin> placePins(Minecraft c, KitConfig config, String dimension) {
        var result = new ArrayList<Pin>();
        for (var place : config.savedPlaces) {
            if (!dimension.equals(place.dimension) || place.mapScope != null && !place.mapScope.isEmpty() && !place.mapScope.equals(ServerDeathSync.scope(c))) continue;
            var pos = BlockPos.containing(place.x,place.cruiseY,place.z);
            result.add(new Pin(place.x,place.z,PLACE,(place.home ? "家 · " : place.mapKind == null || place.mapKind.isBlank() ? "" : place.mapKind+" · ")+place.name,
                List.of(coordinates(pos.getX(),pos.getY(),pos.getZ(),dimension)),null,
                dimension.equals(c.level.dimension().identifier().toString()) ? pos : null));
        }
        if (config.hasDeathPoint && dimension.equals(config.deathDimension) && ServerDeathSync.currentScope(c,config)) {
            var pos = BlockPos.containing(config.deathX,config.deathY,config.deathZ);
            result.add(new Pin(config.deathX,config.deathZ,DEATH,"上次死亡点",
                List.of(coordinates(pos.getX(),pos.getY(),pos.getZ(),dimension),"死亡时间 "+time(config.deathTimeEpochMillis)),
                null,dimension.equals(c.level.dimension().identifier().toString()) ? pos : null));
        }
        return result;
    }

    private Pin nearest(MapViewport view, double x, double y) {
        Pin nearest = null;
        double best = 49;
        for (Pin pin : visiblePins) {
            double dx = view.x(pin.x)-x, dy = view.z(pin.z)-y;
            double distance = dx*dx+dy*dy;
            if (distance <= best) { best = distance; nearest = pin; }
        }
        return nearest;
    }

    public boolean click(Screen parent, Minecraft c, ResourceKey<Level> dimension, MapViewport view, double x, double y) {
        if (c.level != level || !java.util.Objects.equals(dimension, markerDimension) || c.player == null) return false;
        Pin pin = nearest(view,x,y);
        if (pin == null) return false;
        var candidates = visiblePins.stream().filter(other ->
            Math.hypot(view.x(other.x)-x,view.z(other.z)-y)<=7).toList();
        if (candidates.size() > 1) {
            var list = new KitCollectionScreen<Pin>(parent, KitClient.config(), "map-overlapping-pins", "附近地图标记",
                "选择要查看的标记", () -> candidates, value -> value.title,
                value -> String.join(" · ",value.detail), value -> value.title);
            list.onOpen(value -> openPin(list,c,value));
            c.gui.setScreen(list);
        } else openPin(parent,c,pin);
        return true;
    }

    private static void openPin(Screen parent, Minecraft c, Pin pin) {
        var form = new KitFormScreen(parent,pin.title,"Kit 地图标记");
        for (String row : pin.detail) form.note(row);
        var clickedLevel = c.level;
        if (pin.storage != null) {
            var storage = pin.storage;
            form.action("查看记录内容","显示上次开箱快照。",() -> c.gui.setScreen(new StorageDetailScreen(form,storage)));
            form.action("开启指引","在世界中显示保存的坐标。",() -> {
                if (c.level == clickedLevel && StorageLifecycle.canGuide(c,storage))
                    guide(c,pin.title,new BlockPos(storage.x,storage.y,storage.z));
            });
        } else if (pin.guide != null) {
            form.action("开启指引","在世界中标出坐标，方便自行选择路线。",() -> {
                if (c.level == clickedLevel) guide(c,pin.title,pin.guide);
            });
        }
        c.gui.setScreen(form);
    }

    public void open(Screen parent) {
        Minecraft c = Minecraft.getInstance();
        var form = new KitFormScreen(parent,"Kit 地图图层","黄色是记录路线或原目标，蓝色是当前计划。");
        String[] input = {query};
        form.edit("物资搜索","按名称、物品 ID、附魔或备注搜索。留空显示全部仓库记录。",() -> input[0],v -> input[0]=v);
        for (Layer layer : Layer.values()) {
            form.choiceInput(layer.title,"在当前大地图中显示。",new String[]{"显示","隐藏"},
                () -> enabled.contains(layer) ? "显示" : "隐藏",
                choice -> { if ("显示".equals(choice)) enabled.add(layer); else enabled.remove(layer); });
        }
        form.submit("应用到地图",() -> {
            query = input[0].strip();
            if (!query.isBlank()) enabled.add(Layer.STORAGE);
            var config = KitClient.config();
            if (config != null) { config.hiddenMapLayers = hiddenNames(enabled); config.save(); }
            refreshAt = 0;
            c.gui.setScreen(parent);
        });
        form.action("核对投影缺块","读取已加载的服务器区块并生成缺块分布。",() -> auditProjection(parent,c));
        c.gui.setScreen(form);
    }

    /** Every layer is shown unless the user hid it; unknown names from older builds are ignored. */
    static EnumSet<Layer> visibleLayers(java.util.Collection<String> hidden) {
        var visible = EnumSet.allOf(Layer.class);
        if (hidden != null) visible.removeIf(layer -> hidden.contains(layer.name()));
        return visible;
    }

    static java.util.Set<String> hiddenNames(EnumSet<Layer> visible) {
        var hidden = new java.util.LinkedHashSet<String>();
        for (Layer layer : Layer.values()) if (!visible.contains(layer)) hidden.add(layer.name());
        return hidden;
    }

    public void openScenery(Screen parent, Minecraft c) {
        enabled.add(Layer.SCENERY);
        var form = new KitFormScreen(parent,"下一批预加载","查看 Kit 当前选择的方向。");
        var borer = KitClient.borer();
        var current = borer == null ? null : borer.mapScenery(c,null);
        preview = current;
        if (current == null) form.note("当前服务器和维度没有预加载进度。");
        else {
            form.note("已确认 "+current.covered()+" / "+current.total()+" 区块 · 半径 "+current.radius()+" 格");
            if (current.batch() != null) form.note("批次范围 X "+current.batch().minX()+" 至 "+(current.batch().maxX()-1)
                +"，Z "+current.batch().minZ()+" 至 "+(current.batch().maxZ()-1));
            if (current.next() != null) form.note("目标 X "+current.next().getX()+"，Z "+current.next().getZ());
            form.note(current.reason());
            form.note("橙色是未确认区块；缩小时抽样，放大后可看具体缺格。");
        }
        c.gui.setScreen(form);
    }

    public void savePlace(Screen parent, Minecraft c) {
        if (c.player == null || c.level == null) return;
        openPlaceForm(parent,c,c.player.blockPosition(),new String[]{"家","传送门","农场","地点"});
    }

    public void worksite(Screen parent, Minecraft c, int x, int z) {
        refreshProjection();
        var form = new KitFormScreen(parent,"投影施工","选择施工入口或补料点的标记。");
        if (projection == null) {
            form.note(projectionStatus);
        } else {
            form.note(projection.name()+" · 旋转 "+rotationLabel(projection.rotation())+" · 镜像 "+projection.mirror());
            form.note("投影原点 "+projection.origin().toShortString()
                +" · 选点 X "+x+" Z "+z);
            if (projectionCheck == null) form.note("尚未核对缺块。");
            else form.note("橙色显示 "+time(projectionCheck.time)+" 已核对的缺块分布。");
            int y = projection.min().getY();
            form.action("保存选点","可填写实际落脚高度。",() ->
                openPlaceForm(form,c,new BlockPos(x,y,z),new String[]{"施工入口","补料点"}));
            form.action("核对缺块","需要施工范围处于加载距离内。",() -> auditProjection(form,c));
        }
        c.gui.setScreen(form);
    }

    private void auditProjection(Screen parent, Minecraft c) {
        refreshProjection();
        var form = new KitFormScreen(parent,"投影缺块核对","只读取方块与投影。");
        try {
            var audit = ProjectionAudit.scan(c);
            Map<Long,Integer> cells = new HashMap<>();
            for (var element : audit.getAsJsonArray("mismatches")) {
                var row = element.getAsJsonObject();
                if (!"missing".equals(row.get("kind").getAsString())) continue;
                var pos = row.getAsJsonArray("pos");
                int x = Math.floorDiv(pos.get(0).getAsInt(),4)*4;
                int z = Math.floorDiv(pos.get(2).getAsInt(),4)*4;
                cells.merge((long)x<<32 | (z & 0xFFFFFFFFL),1,Integer::sum);
            }
            int totalMissing = cells.values().stream().mapToInt(Integer::intValue).sum();
            projectionCheck = new ProjectionCheck(audit.get("placement_key").getAsString(),audit.get("observed_at").getAsLong(),Map.copyOf(cells));
            enabled.add(Layer.PROJECTION);
            form.note("缺块 "+totalMissing+" 个。返回地图查看分布，颜色越深表示该处缺块越多。");
        } catch (IllegalArgumentException | IllegalStateException unavailable) {
            form.note("未完成核对 · "+unavailable.getMessage());
        }
        c.gui.setScreen(form);
    }

    private static void openPlaceForm(Screen parent, Minecraft c, BlockPos pos, String[] types) {
        var level = c.level;
        var config = KitClient.config();
        if (level == null || config == null || c.player == null) return;
        var scope = ServerDeathSync.scope(c);
        var dimension = level.dimension().identifier().toString();
        String[] kind = {types[0]}, name = {""}, y = {Integer.toString(pos.getY())};
        var form = new KitFormScreen(parent,"保存地图地点",coordinates(pos.getX(),pos.getY(),pos.getZ(),dimension));
        form.choiceInput("类型","家会成为 Kit 的返程目标。",types,() -> kind[0],v -> kind[0]=v);
        form.edit("名称","留空时使用类型和坐标。",() -> name[0],v -> name[0]=v.strip());
        form.edit("高度 Y","填写实际站位或巡航目标高度。",() -> y[0],v -> y[0]=v.strip());
        form.submit("保存",() -> {
            if (c.level != level || !scope.equals(ServerDeathSync.scope(c))) {
                form.message("世界已切换，请重新选点",0xFF7777);
                return;
            }
            int height;
            try { height = Integer.parseInt(y[0]); }
            catch (NumberFormatException invalid) { form.message("高度 Y 需要是整数",0xFF7777); return; }
            String label = name[0].isBlank() ? kind[0]+" "+pos.getX()+" "+pos.getZ() : name[0];
            if (config.savedPlaces.stream().anyMatch(place -> place.name.equalsIgnoreCase(label))) {
                form.message("已有同名地点，请换个名字",0xFF7777);
                return;
            }
            config.saveMapPlace(label, pos.getX()+.5, pos.getZ()+.5, height, dimension, scope, kind[0]);
            c.gui.setScreen(parent);
        });
        c.gui.setScreen(form);
    }

    private static void guide(Minecraft c, String label, BlockPos pos) {
        var guide = KitClient.structureGuide();
        if (guide == null) return;
        guide.start(label,pos.getX(),pos.getY(),pos.getZ());
        c.gui.setScreen(null);
    }

    private static String coordinates(int x,int y,int z,String dimension) {
        return KitConfig.dimensionLabel(dimension)+" · X "+x+" Y "+y+" Z "+z;
    }

    private static String time(long ms) { return ms > 0 ? TIME.format(Instant.ofEpochMilli(ms)) : "未记录"; }

    private static void label(GuiGraphicsExtractor g, Minecraft c, MapViewport view, int x, int y, List<String> lines) {
        var texts = lines.stream().filter(v -> !v.isBlank()).map(v -> KitUi.fit(c.font,v,Math.max(40,view.width()-18))).toList();
        int width = texts.stream().mapToInt(c.font::width).max().orElse(0)+10;
        int height = 8+texts.size()*11;
        x = Math.clamp(x,0,Math.max(0,view.width()-width));
        y = Math.clamp(y,0,Math.max(0,view.height()-height));
        g.fill(x,y,x+width,y+height,0xEE172130);
        for (int i=0; i<texts.size(); i++) KitUi.text(g,c.font,texts.get(i),x+5,y+4+i*11,0xF2F6FD);
    }
}
