# 原登记田块的明确维护补种

此入口只修补用户明确列出的1到4个空格，全部必须仍为原登记同层farmland。不会耕普通草方块/泥土，不开新田，不收割或清除已占用格。

```sh
python farm_reseed_cli.py --registry /absolute/automation/farms/FIELD_KEY/registry.json --cell X FLOOR_Y Z
```

可多次传 `--cell`，最多4个；`--no-move` 使用当前普通交互距离，默认接近路线复用已有`_travel`。收尾复用既有保护停靠，field工作锁保持到收尾结束。

默认接近使用既有有界384格空气路线；超界在创建Client/heartbeat前拒绝。每段原生navigate的意图、初始物品和位置、确切回复与实际到达证明单独保存，未知段不重播。

接近目标为每个明确AIR格的正上方，不从水源中心斜向穿过成熟作物OUTLINE种土。正常可见up面仍由原生普通interact验证。

原registry/hash/layout必须完整，原种植与准备记录已经完成且没有pending/cleanup，旧收获也没有未知动作。原连接可以是已完成的历史连接；本次以实际当前连接进行新维护，绝不采用或重播旧unknown。

两次有界scan确认所有原格仍为farmland，已占用格只能是同crop(age0..7)，只列出的空格是AIR。旧23株仅记为当前观察，origin=`current_connection_observation_not_new_planting`。本次只正常选择实际种子和单次interact，精确种子总量/手持-1与两个不同时间的同crop age0证明通过后才增加`new_reseed`。

原registry和原place24种植回执原字节保持。新`farm-reseed-*.json`记录当前连接、新动作意图、回执和观察；原田目录固定`reseed-active.json`指向维护记录，未知种子选择/种植/导航不能通过新out绕过或重发。完成后的新维护也不是旧24次播种的重放。

唯一窄恢复是已审计Kit2026.10.3.1的精确错误`Target interaction face is occluded or out of reach`。固定host class哈希证明它在visible为空、进入rotation和useItemOn之前抛出。原receipt、完整events、id/world/task/pos/state/hand、全部库存无增量和无其它世界操作须一致；其它错误、缺证据和一般unknown都保留。

```sh
python farm_reseed_cli.py --registry ORIGINAL_REGISTRY --cell X FLOOR_Y Z --journal ORIGINAL_MAINTENANCE --control-dir ORIGINAL_CONTROL reconcile-rejected
python farm_reseed_cli.py --registry ORIGINAL_REGISTRY --cell X FLOOR_Y Z --journal ORIGINAL_MAINTENANCE --control-dir ORIGINAL_CONTROL --archive-verified reconcile-rejected
```

第一条只读核验；第二条仅归档精确无use拒绝与原字节，标`rejected_without_use`且`new_reseed=0/complete=false`，关闭原动作后需要从当前新鲜空格的新维护scope再开始。跨连接也只可沿用这份原精确拒绝证据，不采用当前库存推算旧成功。运行中同样的已证实前置拒绝不会重复use；健康且没有未决世界动作的等待使用既有allow_settled_wait保护停靠，而不是关闭heartbeat把责任交给logout。
