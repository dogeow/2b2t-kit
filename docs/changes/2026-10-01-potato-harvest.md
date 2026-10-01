# 有界土豆收获、补种助手

`decision-runtime/potato_harvest.py` 接收调用者已持有的 `MaterialClient`，复用实际材料租约及心跳；不会创建控制器、移动、重连或解除安全锁。已有水源、支撑、光照、耕地和所有作物均须在新扫描中成立。

```python
from potato_harvest import run

result = run(client, {
    'authorized': True,
    'center': [761021, 63, 797869],  # 水源/耕地所在的 Y
    'radius': 2,
    'bonemeal': False,
}, output_directory, checkpoint, max_cells=4, bonemeal_budget=0)
```

默认仅收获水源四个轴向邻格。也可提供唯一的 `cells` 耕地坐标列表，必须处于声明的半径 1..2 地块内；每次最多处理四格。玩家位置由调用者事先安排，助手只检查保守交互距离。

每格仅在最新精确 `potatoes[age=7]` 状态发送一次普通 `mine_block`。破坏前保存物品实体 ID，破坏后只接受与同帧附近实体数据吻合的新土豆/毒土豆掉落，且必须处于该格附近。自动拾取最多等六秒，两个不同扫描时间均须证明该格为空及真实携带土豆数量增加；瞬间拾取以空的事前区域扫描、单次作物破坏及实际库存增量作为因果范围。不会猜测掉落数量。未拾取返回 `WAIT_LOOT`，不移动或追加破坏。

补种使用最新空位、耕地与真实手持土豆，两个不同扫描时间须证明年龄为零及库存精确减少一颗，保持至少四颗携带储备。区域内其它作物始终须保持土豆；年龄可以自然增长。已证明属于本次收获的毒土豆可留在原格附近，未拾取土豆阻止下一次破坏。

骨粉为显式选项：`bonemeal=True`，每格最多四次、全轮最多十六次。每一次普通 `interact` 均须看到真实骨粉减一、手持数量相同变化和两个新帧的年龄增长，才允许下一步；回执自身不证明成功。

每个单次动作发送前写入原子 journal。未知回执、手动操作、世界/租约变化、受伤或证据缺失会停止。存在 `pending` 的 journal 不重发动作；完成的 journal 不启动新一轮。调用者必须明确检查未完成状态，并为新轮次提供新的输出目录。所有成功标记均为已加载客户端观察，`server_verified=False`，不声称逐格服务端 ACK。

验证：`python3 -m unittest test_potato_harvest`（在 `decision-runtime/`）。纯 Python 助手没有 Java/版本/部署改动，真实游戏验收由唯一调用控制器完成。
