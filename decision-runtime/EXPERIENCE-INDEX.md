# 已保留的自动化经验

通用做法保留为代码与回归测试；现场证据保留在动作日志和案例中。只读观察器与材料控制器的记录钩子共用本地技能库，不调用模型。回顾文档和 AI 总结只作经验，不会自动晋升为已验证技能。

| 经验 | 实现 | 当前验证范围 |
|---|---|---|
| 施工与补货不能把搜索预算用尽当作无路 | `DefaultBuildNavigation`、`BuildSupplyTask` | 分帧搜索测试；多人服寻路与续建实测 |
| 窄门精确到位与浮点误差边界 | `DefaultBuildNavigation.motion` | 真实坐标回归；1.7.58 热更新后拾取与地下室补建成功 |
| 按入库记录取回成品，不能把“访问箱子完成”当作材料齐全 | `stored_supplies.py` | 已从两处仓库取回成品，并检查数量增量 |
| 楼梯间中转、开门通行、开地下室活板门 | `projection_transit.py`、`door_access.py`、`projection_access.py` | 多人服通过后恢复门状态；保留玩家容器 |
| 按图纸轴向放原木再去皮 | `projection_wood.py` | 5 根新木梁与 1 根已有原木去皮实测；不可见交互面保留待处理 |
| 局部装修采用真实支撑面与短批打印 | `local_printing.py` | 卧室补齐 16 格；灯具相关批次补齐 9 格 |
| 先核对并回收掉落物，再补回被清理地形 | `projection_terrain.py`、`drop_collection.py` | 地下室后续补齐 18 格；未覆盖所有复杂封闭位置 |
| 更新前比较实际安装包，只改引擎不重启 | `release_scope.py`、`hot_update.py` | 文件差异、版本、连续会话与失败回退检查 |
| 精确取少量材料、潜影盒原位归还 | `inventory_exact.py`、`packed_supplies.py` | 两只潜影盒正常归还，第三只因掉落物内容不可见而漏捡，由用户回收；身份判定与收尾修复已通过测试，待实机复测 |
| 新接口经验捕获 | `experience_recording.py`、`kit_skills` | 隔离实例目录选择、控制参数剥离、会话核对与直接记录测试 |
| 野外大投影先扫描完整地基和净空，离线处理图纸前安全下线；飞离旧战斗 48 格后明确记录脱离，不误报击杀 | `projection_site.py`、`material_client.py`、`BorerRangedCombat.java` | 星舰选址现场只读扫描；安全下线确认；远距战斗脱离修复待热加载实测 |
| 托管材料会话可核对后吃一件快捷栏食物；混凝土粉末批次锁定同一格、需核对挖回成品及水流漂走的掉落物 | `AutomationBridge.java`、`ConcreteMaker.java`、`ConcreteDropPolicy.java` | 进食、第一批 64 粉末取料、单块制作及独立拾回 25 个掉落物已在多人服实测；批次自动拾回待实机复测 |
| 熔炉界面仅由同一受保护会话操作；长时间烧炼时关界面保持 PvE 防护，按服务端输入／燃料／输出和背包增量验收 | `AutomationBridge.java`、`material_client.py`、`craft_recipe.py` | 高炉 114 生铁、普通熔炉 64 石头、16 高炉与 33 漏斗地基实测；星舰审计 128/3407，尚未完成 |
| 水下沙砾采用由近及远扫描、装备属性初始氧气预算和生产性返气校准；本机命令取代界面点击，漂流掉落物有限次水面重新定位 | `GravelCollector.java`、`EquipmentAirBudget.java`、`kit_cli.py`、`kit_release.py`、`cases/20260926-native-gravel-lessons.json` | 1.9.96 多人服短批 4 块实收、满血高空收尾；有一次漂移拾取首轮未确认，长期无人值守尚未验收 |
| 开箱需等待实际内容同步；干燥沙堆复用原生 AREA 批采，健康余量退出即保留人工恢复锁 | `container_access.py`、`native_sand_quarry.py`、`MaterialQuarryPolicy.java`、`safety_interlock.py` | 沙砾入库 946；原生采沙使背包达到 642，随后受伤至 18.9、升至 Y110 下线；AREA 苦力怕撤离与区域断点隔离修复已离线测试，待人工恢复后热加载实测 |

| 轻伤暂停和紧急下线分开；Jev 从已核验候选中选择，紧急避险不等模型；沙地短转场不再固定升高 25 格 | `decision_advisor.py`、`material_client.py`、`native_sand_quarry.py`、`cases/20260926-jev-recovery-quarry.json` | 67 项相关测试；Jev 479.7 ms 选择完整沙地后 35.88 秒实收 44 沙子、全程满血；已热加载 1.7.64，但并非所有 Kit 模块已接入 Jev |

| 合成按完整批次布置九宫格，结合原料入格后腾出的空间；补货与存成品逐堆交替 | `stack_recipe.py`、`material_manufacture.py`、`material_depots.py` | 多人服已实测 207 骨粉、208 染料、单批 512 白色粉末；输入/输出逐批守恒核对，连续凝固仍在进行 |

| 含水树叶封闭工位，按真实余额续作；先回站位再经自有顶孔升空；对齐不强求不可发送的微小高度差 | `concrete_shelter.py`、`concrete_soil.py`、`DefaultBuildNavigation`、`cases/20260926-concrete-batch-enclosure.json` | 1.7.65 热加载与 1008 项 Java 测试通过；封闭工位 8 块试跑、修正后的退出实测满血，后续长批生产在进行 |

最近一次完整图纸检查为 **2678 / 2880** 个方块匹配。房屋仍未完成；实体、旗帜图案及剩余方块需单独验收。不能将以上单项成功描述成任意服务器通用或长期无人值守安全。

观察器状态：`companion-skills/state/observer-status.json`；本地经验：`companion-skills/state/skills.sqlite3`。这些现场数据不进入 Git。源码、案例和测试进入 Git；新代码尚未推送时，仍会明确区分本地保存与远端备份。

- 2026-09-26：顶部作业总进度、Jade 动态避让、会话变更清理：[案例](cases/20260926-work-hud-jade.json)；[接入说明](WORK-HUD.md)。

- 2026-09-26：离线八项改进、配料点击成本、容器会话隔离、低顶防御、Jev 退避与发布配套校验：[改进记录](../docs/changes/2026-09-26-offline-kit-improvements.md)。
