# 海水直接装瓶

Minecraft 26.1.2 的 `BottleItem.use` 使用 `SOURCE_ONLY` 视线取水，生成带 `Potions.WATER` 组件的水瓶，水源保持不变。沿海制泥不需要先取桶水、补炼药锅再装瓶。

宿主 2026.10.10.2 增加 `bottle_water_protocol: 1` 和 `bottle_fill`。请求使用现有材料任务控制权，提供 `pos`、精确 `expected_state: Block{minecraft:water}[level=0]` 和 `expected_hand: minecraft:glass_bottle`。通过正常 `gameMode.useItem` 交互，不调用放置方块接口。实际 Minecraft 26.1.2 本地 JAR 已核对。

接口拒绝未加载的服务器区块、超距离／遮挡、人工移动、库存变化、液体内站位以及附近效果云。单瓶直接在原手持槽变成水瓶，满背包也可以使用；堆叠瓶需要实际空槽，避免原版丢出无法放入背包的成品。每次只发送一次，发送前保存持久记录。

完成证据要求同连接的服务器库存包确认手持槽及新增水瓶槽，水瓶的完整组件必须匹配原版水瓶，整份库存按预期精确变化，预测已结束，水源仍保持 level=0，后续稳定八 tick。取水不会更改水源，所以不等待不存在的水方块变化包。超时或停止保留未明结果，不自动重发。库存整包现逐一转发全部携带槽，原桶接口仍只接受自己的选中槽证据。

`mud_pipeline` 优先调用 `mud_water_supply.fill_bottle`，复用已登记海水源与干燥接近点。海水源已登记时，旧宿主需更新、源变化或未明结果不会回退炼药锅。仅没有登记海水源的既有配置保留原炼药锅路线。新水瓶槽身份纳入原制泥流水账，旧药水不直接当水瓶。

当前实机登记水源 `[761043,62,797880]`，接近点 `[761043.5,63.1,797879.5]`。近距离保持短平移及干燥下降，不重新升到巡航高度。旧失败任务 `map-full-kit-singleton-bottle-7695-015` 已结束，不能当作活跃进程或重播旧制作步骤；当前实物另外核到泥砖34、压实泥4、空瓶1。

验证：1899 项 Java 测试通过，主包及运行引擎校验通过；直接海水路线、旧宿主、源变化、水瓶组件、未明结果和不重发均有针对回归。部署需要一次完整游戏重启。代码／测试完成不等于当前服务器取水完成，安装和实机回执另存独立证据。

后续实机：宿主2026.10.10.2已正常安装并重新上线，`bottle_water_protocol=1`。本轮图面累计新增92格，完整当前服务器复核为8950／16512。首次装瓶前复核发现旧水点 `[761043,62,797880]` 已变成沙子，原任务原生事件中没有 `bottle_fill`，空瓶未消耗，旧 pending 保留。

附近256格实际扫描确认新水源 `[761044,62,797879]`，距原干岸站位眼睛约2.43格；原站位仍为干燥沙岸且身体空间为空。备份原材料配置后仅更新水点与当前观测信息。新点未执行水桶取水，不沿用旧点的 `renewing_source_server_verified` 信用；水瓶取水不需要该信用。证据在 `work/live-20261004/mud-sea-source-current-sand-survey-7622-001/updated-source-proof.json`。新完整地图任务正在使用这项登记，实际水瓶回执另行核对。

当前服务器实机装瓶通过：请求 `materials-4f9e2a6e55b3`、世界 `7622657d-39a9-4368-b2e0-aded76acb0f6`，原手持空瓶槽6变为完整水瓶，`confirmed=true`、`unknown_outcome=false`，手持槽与水瓶槽服务器确认均为true，水源保持不变。流水线随后通过原 owned-dirt 转泥和采集验证，实际新增泥1，没有炼药锅或桶补水动作。独立观测保存于 `work/live-20261004/direct-sea-bottle-host2-ready-7695-001/actual-current-water-bottle-proof.json`，原流水线原生回执保留在 `map-full-kit-current-sea-source-7622-019/material-job/pipelines/000002-mud_bricks/mud-pipeline.json`。全图仍未完成。
