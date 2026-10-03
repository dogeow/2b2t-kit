# 共用小田地准备入口

新增 `farm_preparation.py`、`farm_preparation_cli.py` 与 `kit_cli.py farm prepare`。土豆、小麦共用田地准备记录；耕地、播种仍由既有 `farm plant --crop potato|wheat` 执行。准备模块不创建种植循环、不调用模型、不操控 UI。

```sh
python decision-runtime/kit_cli.py farm prepare --center 761029 64 797869 --radius 2
python decision-runtime/kit_cli.py farm prepare --center 761029 64 797869 --radius 2 --water-source 761043 62 797867
python decision-runtime/kit_cli.py farm plant --center 761029 64 797869 --radius 2 --crop wheat
```

以上为入口用法，本次未执行游戏命令。`center` 是未来中心水源所在的土层整数坐标；半径只接受 1、2，对应 8、24 个种植位。中心已有实际 `Block{minecraft:water}[level=0]` 时跳过取水和放水，不需要携带水桶。否则使用携带水桶，或只从 `--water-source X Y Z` 明确声明的现有水源正常取水；不搜索或推断水源。声明水源限定在中心水平 32 格、垂直 16 格内。

可使用 `--max-torches 1..4` 限制本次补光，默认 4；`--no-move` 要求各交互目标已经在范围内。默认接近复用现有 `material_jobs.acquisition._travel` 的详细空气路径扫描与正常 Kit `navigate air_only`，保留水平 32 格范围及已验证的 `2.32/5.1` 路线余量，不另设垂直 64 格限制或独立飞行循环。薄代理为每次导航记录 intent 并保留稳定停靠验证；不自动挖路。缺少稳定导航或原生桶协议会停止。正常完成复用现有材料防护收尾；未知停靠结果也保留准备记录。

## 扫描与修改边界

每次使用真实 `details=True` 扫描，要求 `phase=done`、已加载区块、类型完整的方块元数据和已知扫描实体范围。`scan_coherent=false` 表示分多个客户端 tick 采样，不能据此判为不完整：必须是原生 `loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot` scope，`scan_cells_read=scan_total_cells=请求的完整闭区间体积`，start/end/current revision 一致，时间和 tick 范围正向一致且不超过 30 秒/600 ticks。单 tick coherent 扫描同样要满足该元数据契约。世界与当前控制归属继续由 `_gate` 核对；最终仍需两次不同时间审计，不声称原子服务器快照。扫描中的容器、方块实体、已有作物/耕地、中心以外的流体和实体均受保护。

种植位必须是同层天然 `grass_block/dirt`，下方为已观察的天然干燥实心块，头部两格净空。只允许清除 `short_grass`；其它植物或障碍会停止。水坑要求干燥实心底和四个天然土壁；只挖一个中心草土块，不挖种植土或四壁。

`mine_block` 完成必须有匹配目标、服务器方块更新和原生序列 ACK，再扫描确认目标为空。`bucket_fill/place` 必须有匹配 request/world/operation/pos 的现有 `bucket_water` 回执，且一次正常使用、目标方块与选中桶槽服务器确认、明确非未知结果、精确空桶/水桶数量转换和当前手持桶一致；仅 `phase=done` 不够。

补光候选是田地外侧四个方向的少量站位，读取实际支持面高度，允许支持面比田地低一格；只在天然干燥草土上正常放火把，不覆盖种植位。每次放置记录两次不同时间的完整扫描和精确火把库存减少，不复用一帧结果。最后再次两帧检查实际水源、所有种植位净空和逐位 `spawn_block_light>=9`。火把距离或布局不构成光照证明；缺少光照字段不会先修改世界，放完预算后仍不足则返回 `WAIT_LIGHT`。

## 状态与恢复

作物无关登记位于实际游戏自动化根的 `farm-preparation/<center-key>/registry.json`，绑定规范化 server、dimension、center、radius、明确水源、游戏 session 和原始 journal 目录。中心锁也阻止变更半径绕开同一水坑的动作。改变 `--out`、水源、半径或游戏 session 会拒绝自动接管，需人工核对和明确恢复。

控制取得、选物品、移动、清草、中心挖土、桶操作、火把及收尾都先持久化 intent；未知结果保持 `pending` 或独立 `cleanup_pending`，后续运行不重发，也不自动用扫描擦除它。已完成后又消失的水源、火把或重新出现的土/草也不会自动重复原动作。

准备入口还检查既有土豆、小麦登记的未决种植动作。模块导出只读 `assert_preparation_resolved(root,state,request)`，供其它种田入口在创建控制器前阻断未决准备记录。种植入口已先持有同一个 `preparation_lock`，再调用此 hook，并一直持锁到收尾，避免并发绕过。当前控制器已持锁时，hook 只读取登记和 journal；不重新尝试锁。

防护收尾不要求原生 `KEEP_PVE_GUARD` 回执一定包含 snapshot。以匹配当前 lease/job 的原回执，加 `client.raw()` 新鲜世界、revision、血量、防护、Flight、停车目标和 parking lease 检查完成收尾；将新观察附在 journal 中，保留原回执的 `confirmed=false`，不会改写成服务器确认。

本次验证仅运行临时目录和模拟原生回执的 Python 测试，未部署、重启、操控游戏或修改版本。桶/mining 有原生服务器证据；火把及最终光照是当前已加载客户端扫描证据，整体输出明确 `server_verified=false`。实机取水/放水、光照传播、导航和防护停靠仍未验收。
