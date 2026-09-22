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
| 精确取少量材料、潜影盒原位归还 | `inventory_exact.py`、`packed_supplies.py` | 单元测试通过；新版潜影盒完整流程仍待实机验收 |
| 新接口经验捕获 | `experience_recording.py`、`kit_skills` | 隔离实例目录选择、控制参数剥离、会话核对与直接记录测试 |

最近一次完整图纸检查为 **2678 / 2880** 个方块匹配。房屋仍未完成；实体、旗帜图案及剩余方块需单独验收。不能将以上单项成功描述成任意服务器通用或长期无人值守安全。

观察器状态：`companion-skills/state/observer-status.json`；本地经验：`companion-skills/state/skills.sqlite3`。这些现场数据不进入 Git。源码、案例和测试进入 Git；新代码尚未推送时，仍会明确区分本地保存与远端备份。
