# 从已照亮的安全邻地补光

分区审计曾发现暗沙地 `[760824,62,797823]` 上方 Y65 有屋顶，因此原候选规则不会直接在此放火把。邻地 `[760821,62,797824]` 已有 3 级方块光、柱顶无屋顶且允许放置；其火把位置至暗地的出生空间有已知空气通路，可以从外侧继续照亮暗处。

纯批次规划默认同时考虑这种安全邻地。它仍要求原允许的完整支撑方块、无液体／方块实体、登记范围、保护掩码和无屋顶柱；已照亮邻地只有经当前完整扫描的光传播模型证明能正向覆盖实际未保护暗点时才进入批次。每条边衰减 1；已知空气和下述两个精确植物状态可传光，其它非空气格及保护区均不进入预测通路，超出扫描范围不当作空气。不能找到安全通路时不生成选项；不拆屋顶、树木或其它方块。

批次上限和库存约束保持不变。执行仍重新检查实际支撑与完整柱、实体及移动通路，使用原生交互，再验证两帧实际火把与库存减 1。规划预测不代表放置成功或暗点已解决；补光后仍需完整实际灯光审计。`residual=False` 可保留原先仅从暗支撑选点的纯规划行为。

## 两种植物的纯光传播证据

实际审计有短草和蒲公英占据暗地上方出生空间。它们属于非空气方块，但将其全部当作不透光会漏掉可以从安全邻地照亮的暗点。此处只接受完整详细扫描中的 `Block{minecraft:short_grass}`、`Block{minecraft:dandelion}` 两个精确状态，且必须明确 `fluid=false`、`block_entity=false`、`solid=false`、`passable=true`。属性后缀、其它植物、玻璃或仅有空碰撞的任意方块均不自动扩大白名单；缺少或矛盾的详情也不传光。保护掩码仍切断通路。

光学结论来自当前 Minecraft **26.1.2** 的本地原始类和映射后源码，未根据 `passable` 推断光阻：

- 源码归档：项目 `.gradle/loom-cache/minecraftMaven/net/minecraft/minecraft-common-043a8b3edf/26.1.2/minecraft-common-043a8b3edf-26.1.2-sources.jar`。
- `Blocks.java:633–645,831–841`：短草为 `TallGrassBlock`，蒲公英为 `FlowerBlock`，均登记 `noCollision()`；`BlockBehaviour.java:1072–1076` 明确该属性同时设置 `canOcclude=false`。
- `TallGrassBlock.java:18–37`、`FlowerBlock.java:19–48`：均继承 `VegetationBlock`，自身选择轮廓分别为 `Block.column(12,0,13)` 与 `Block.column(6,0,10)`，并非空轮廓；无额外光阻或光面遮挡覆盖。`VegetationBlock.java:49–52` 对无流体状态返回 `propagatesSkylightDown=true`。
- `BlockBehaviour.java:228–230,304–309,503–527`：光面形状开关默认关闭；`canOcclude=false` 使用空遮挡形状而 `solidRender=false`，因此这两种状态的 `getLightDampening()` 为 **0**。
- `LightEngine.java:62–84`：`!canOcclude || !useShapeForLightOcclusion` 使光面遮挡为空，但进入每格的实际光阻为 `max(1,getLightDampening())`。`BlockLightEngine.java:50–68` 从来源等级扣除此值并检查相邻面。故经过两种植物的六向方块光传播均衰减 **1** 级；它们不会让 14 级火把越过原有距离与出生光阈值限制。
- 已用捆绑 JDK 25 的 `javap -classpath /Applications/.minecraft/versions/26.1.2/26.1.2.jar -c -p` 检查实际游戏 Jar 的 `Blocks`、`BlockBehaviour$Properties`、`BlockBehaviour`、`VegetationBlock`、`LightEngine`，确认上述登记、`canOcclude`、无流体天光规则与 `max(1,...)` 字节码相符。原生扫描 `AutomationBridge.scanCell` 目前没有直接输出光面形状或光阻字段，因此这两个 ID 的版本固定源码证据是白名单依据。

此白名单仅修改离线光传播图：可以穿过植物或预测植物所在出生空间的照度，不能将植物转为空气、选择植物作为支撑、在其位置放火把、忽略屋顶／柱内障碍，或改变实机移动与施工校验。扫描原始内容保持原样，实际光照仍以补光后的服务器审计为准。

针对测试覆盖两种植物位于暗点时的邻地补光、双向传播与每格衰减、非白名单及矛盾详情拒绝、保护区阻断，以及候选支撑／火把位置／柱内净空规则保持不变。
