# 投影空中种子

`projection_air_seed_protocol=1` 是宿主接口；安装包含此接口的主包后需要完整重启，热加载引擎不能新增入口。

当前材料租约需要健康、空闲、PvE 防护。已选投影必须锁定；玩家应已安全飞到种子正常交互距离内，主手拿着该格投影所需的完整普通方块。Meteor **player.AirPlace** 和 Flight 必须已开启，接口不会切换模块或设置。

```python
result = client.request(
    'projection_air_seed',
    placement_key=current_status['projection_selection']['key'],
    target=[761024, 64, 797631],
    expected_state='Block{minecraft:cobblestone}',
    expected_item='minecraft:cobblestone',
)
```

目标须是当前已加载服务器区块中的实际空气，投影内可见、无实体、无视线遮挡。接口仅支持无属性、无重力、无流体、无方块实体的完整方块；不负责移动、切换材料或大面积铺设。

构造的 hit 与实际 Meteor AirPlace 相同：指定目标格、格中心、玩家水平朝向的反面、inside=false。它直接调用一次 Meteor `BlockUtils.interact(hit, MAIN_HAND, true)`，不使用模块旧红框缓存，也不依赖相机 UI 的静默旋转。不会伪造方块、成功状态或物品。

确认需要当前连接收到该格的匹配服务器方块更新、实际状态仍正确、所需材料数量恰好减少一，并稳定等待八个客户端 tick。最多等待一百 tick；纠正包会取消确认，未确认返回 `waiting`，不会发送第二次。同一世界会话、同一格的已尝试种子不能自动重开。

终态 `projection_air_seed`（快照为 `last_projection_air_seed`）包含目标、投影键、使用次数、材料数量、服务器确认及范围。`module_settings_changed=false`：接口不改变用户模块配置，结束后 PvE 防护保持。

种子确认后使用相邻支撑继续普通打印。ProfessionalPrinter 现在正确识别 player.AirPlace，为避免两个放置器同时作用，开始打印前需要由拥有这次模块设置的控制者关闭 AirPlace；只恢复自己改过且未被用户另行修改的设置。
