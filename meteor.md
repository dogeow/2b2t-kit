# Meteor 功能索引

写 twob2tkit 新功能之前先查这里，别再造已经有的轮子。

来源是本机 `meteor-client-source/`（面向 **26.2**，twob2tkit 是 **26.1.2**，API 签名可能对不上，
但**有没有这个功能**这件事是准的）。要确认细节就直接看：

```text
meteor-client-source/src/main/java/meteordevelopment/meteorclient/systems/modules/<分类>/<模块>.java
```

模块名下面写的是 Meteor 里的 kebab-case 名字，游戏里搜这个名字就能找到。

---

## 1. 决策流程

1. **先查表**：本文第 3 节按分类列了全部模块。拿不准就 `rg` 一下 `meteor-client-source`。
2. **有就用**：Meteor 已经做了的，twob2tkit 不要再写一份。界面上引导用户去开 Meteor 对应模块即可。
3. **不够就增强**：Meteor 有但缺了关键部分，写**补齐差额**的那部分，并让两边能共存——
   给一个「这块交给 Meteor」的开关，本模块在开关关闭时不抢视角、不抢按键、不抢攻击充能。
   现成的正面例子是 `KitConfig.brawlerMeleeEnabled`：关掉之后 `PiglinBrawler`
   只做 KillAura 不做的事（反弹恶魂火球、拉弓、飞行拉扯），近战完全让给 KillAura。
4. **确实没有才新写**：写完回来更新第 4 节的对照表。

判断「够不够」的标准是功能缺口，不是代码风格。Meteor 的 `auto-breed` 已经能喂动物繁殖，
就算它的实体过滤不如你想要的细，也应该是给它补一层，而不是重写一个 `AutoFeeder`。

---

## 2. Meteor 会抢的东西（写任何自动化都要考虑）

| 抢什么 | 谁抢 | 后果 |
| --- | --- | --- |
| 视角 | `kill-aura`、`bow-aimbot`、`rotation`、`arrow-dodge` | 巡航/瞄准被改朝向，需要 `MinecraftTickTailMixin` 写回 |
| 跳跃键 | `anti-afk` 的 `jump` 动作 | 每 tick 强制松开跳跃键，玩家手动按空格也跳不了 |
| 潜行 / 左右键 | `anti-afk` 的 `sneak`、`strafe` | 自己蹲下、自己左右横移 |
| 换工具 | `auto-tool` | 和本 mod 的 `selectTool` 互相抢槽位 |
| 换武器 | `auto-weapon` | 同上 |
| 攻击充能 | `kill-aura` | 两边都挥手会互相重置充能条，伤害反而更低 |
| 主手物品 | `auto-replenish`、`chest-swap`、`offhand` | 拉弓/放置到一半被换掉 |

---

## 3. 模块清单

### Combat

| 模块 | 说明 |
| --- | --- |
| `anchor-aura` | 自动放置并引爆重生锚伤害实体 |
| `anti-anchor` | 头顶放台阶，防别人对你用 Anchor Aura |
| `anti-anvil` | 在你和铁砧之间放方块，防 Auto Anvil |
| `anti-bed` | 放线防止别人在你身上放床 |
| `arrow-dodge` | 尝试躲开飞来的箭 |
| `attribute-swap` | 攻击时切到指定槽位 |
| `auto-anvil` | 在玩家头顶放铁砧砸头盔 |
| `auto-armor` | 自动装备护甲 |
| `auto-city` | 自动挖别人脚边的方块 |
| `auto-exp` | PvP 里自动修护甲和工具 |
| `auto-log` | 满足条件时自动断线 |
| `auto-totem` | 副手自动补图腾 |
| `auto-trap` | 用方块把人困住 |
| `auto-weapon` | **自动切到快捷栏里最合适的武器** |
| `auto-web` | 给别人放蜘蛛网 |
| `bed-aura` | 下界/末地自动放床炸人 |
| `bow-aimbot` | 弓自动瞄准 |
| `bow-spam` | 疯狂放弓/弩 |
| `burrow` | 把自己卡进方块 |
| `criticals` | 攻击时打出暴击 |
| `crystal-aura` | 自动放并炸末影水晶 |
| `hitboxes` | 放大实体判定箱 |
| `hole-filler` | 用指定方块填洞 |
| `kill-aura` | **自动攻击周围指定实体**（不需要准心对准，射程可调） |
| `offhand` | 副手固定拿指定物品 |
| `quiver` | 朝自己射箭 |
| `self-anvil` / `self-trap` / `self-web` | 在自己身上放铁砧 / 头顶方块 / 蜘蛛网 |
| `surround` | **脚下四周放黑曜石防水晶爆炸**（注意：只防脚下，不是把人整个封起来） |

### Movement

| 模块 | 说明 |
| --- | --- |
| `air-jump` | 空中可跳 |
| `anchor` | 到洞口上方完全停住，方便进洞 |
| `anti-void` | 尝试防止掉进虚空 |
| `auto-jump` | **自动跳跃** |
| `auto-walk` | **自动向前走** |
| `auto-wasp` | 朝目标直线飞（不会绕障） |
| `blink` | 暂存移动包实现瞬移 |
| `click-tp` | 传送到点击的方块 |
| `elytra-boost` / `elytra-fly` | 鞘翅助推 / 鞘翅飞行增强 |
| `entity-control` | 无鞍也能控制坐骑 |
| `fast-climb` | 爬梯更快 |
| `flight` | **飞行**（twob2tkit 的巡航就是建立在这个之上的） |
| `gui-move` | 开着 GUI 也能操作 |
| `high-jump` / `long-jump` | 跳更高 / 跳更远 |
| `jesus` | 水上行走 |
| `no-fall` | 防摔伤 |
| `no-slow` | 用物品时不减速 |
| `parkour` | 到方块边缘自动跳 |
| `reverse-step` | 下落更快 |
| `safe-walk` | 不会走出方块边缘 |
| `scaffold` | **脚下自动铺方块** |
| `slippy` | 改方块摩擦力 |
| `speed` | 改地面移动速度 |
| `spider` | 爬墙 |
| `sprint` | 自动疾跑 |
| `step` | 直接走上整格 |
| `trident-boost` | 三叉戟激流助推 |
| `velocity` | 免击退 |

### Player

| 模块 | 说明 |
| --- | --- |
| `air-place` | 隔空放置 |
| `anti-afk` | **防挂机踢：随机跳、挥手、潜行、横移、转圈**（会抢按键，见第 2 节） |
| `anti-hunger` | 减少饥饿消耗 |
| `auto-clicker` | 自动点击 |
| `auto-eat` | **自动吃东西** |
| `auto-fish` | **自动钓鱼** |
| `auto-gap` | 自动吃金苹果 |
| `auto-mend` | 副手修满后自动换下一件 |
| `auto-replenish` | 快捷栏/主手/副手自动补货 |
| `auto-respawn` | 死后自动重生 |
| `auto-tool` | **自动切到最合适的工具** |
| `break-delay` | 改挖掘间隔 |
| `chest-swap` | 胸甲和鞘翅一键互换 |
| `exp-thrower` | 自动扔经验瓶 |
| `fake-player` | 生成假人用于测试 |
| `fast-use` | 极快使用物品 |
| `ghost-hand` | 隔墙开容器 |
| `instant-rebreak` | 同一位置瞬间重挖 |
| `liquid-interact` | 可与流体交互 |
| `middle-click-extra` | 中键触发各种动作 |
| `multitask` | 用物品的同时可攻击 |
| `name-protect` | 隐藏玩家名和皮肤 |
| `no-interact` | 屏蔽指定交互 |
| `no-mining-trace` | 隔着实体挖方块 |
| `no-rotate` | 屏蔽服务端下发的转向 |
| `no-status-effects` | 屏蔽指定状态效果 |
| `portals` | 传送门里也能正常开 GUI |
| `potion-saver` | 站着不动时药效不走 |
| `reach` | 加长交互距离 |
| `rotation` | 锁定/修改朝向 |
| `speed-mine` | 挖得更快 |

### World

| 模块 | 说明 |
| --- | --- |
| `ambience` | 改环境配色 |
| `auto-breed` | **自动喂食指定动物繁殖**（可配实体列表、范围、用哪只手、成年/幼年过滤） |
| `auto-brewer` | 自动酿造 |
| `auto-mount` | 自动骑乘 |
| `auto-nametag` | 自动挂命名牌 |
| `auto-shearer` | 自动剪羊毛 |
| `auto-sign` | 自动写告示牌 |
| `auto-smelter` | 自动熔炼背包物品 |
| `build-height` | 建筑上限处也能交互 |
| `collisions` | 给某些方块加碰撞箱 |
| `echest-farmer` | 放/挖末影箱刷黑曜石 |
| `enderman-look` | 盯着或避开末影人 |
| `excavator` | **挖空一个选定区域** |
| `flamethrower` | 点燃活体食物 |
| `highway-builder` | **自动修高速路** |
| `infinity-miner` | **无限挖矿：耐久低了就去挖修复方块**（需要经验修镐） |
| `liquid-filler` | 填掉范围内的流体源 |
| `no-ghost-blocks` | 防幽灵方块 |
| `nuker` | 挖掉周围方块 |
| `packet-mine` | 用包挖方块，无动画 |
| `spawn-proofer` | 自动给暗处放置防刷怪方块 |
| `stash-finder` | **扫已加载区块找storage方块，结果存文件** |
| `timer` | 改游戏速度 |
| `vein-miner` | **连锁挖同种方块** |

### Render

| 模块 | 说明 |
| --- | --- |
| `better-tab` / `better-tooltips` / `boss-stack` / `blur` | 界面增强 |
| `block-esp` / `storage-esp` / `city-esp` / `hole-esp` / `void-esp` / `tunnel-esp` | 各种方块透视 |
| `esp` / `chams` / `tracers` / `nametags` / `entity-owner` / `pop-chams` | 实体透视与标注 |
| `block-selection` / `break-indicators` / `hand-view` / `item-highlight` / `item-physics` | 交互与物品渲染 |
| `breadcrumbs` / `trail` / `logout-spots` / `marker` | 轨迹与标记 |
| `waypoints` | **路点系统** |
| `freecam` / `free-look` / `camera-tweaks` / `zoom` | 视角 |
| `fullbright` / `light-overlay` / `wall-hack` / `xray` | **亮度与透视挖矿** |
| `no-render` / `time-changer` / `weather-changer` / `trajectories` | 其它 |

### Misc

| 模块 | 说明 |
| --- | --- |
| `anti-packet-kick` / `auto-reconnect` / `server-spoof` / `packet-canceller` / `packet-logger` | 连接与协议 |
| `better-chat` / `spam` / `message-aura` / `notifier` / `sound-blocker` | 聊天与提示 |
| `better-beacons` / `inventory-tweaks` | 信标与背包 |
| `book-bot` / `notebot` / `discord-presence` / `swarm` | 其它 |

---

## 4. twob2tkit 与 Meteor 的对照

### 4.1 已知重复，应该收敛（欠债）

| twob2tkit | Meteor | 现状 |
| --- | --- | --- |
| `AutoFeeder` | `world/auto-breed` | **部分重复**。Meteor 只喂**手上已经拿着的**饲料，不走近、不换背包、没有种类顺序。本模块多了走近、换槽、喂完收起、按顺序喂（没对应饲料就跳到下一种）。不要两边一起开 |
| `BorerItems.selectWeapon` | `combat/auto-weapon` | 重复。开着 `auto-weapon` 时两边会抢槽位 |
| `AutoChopper.selectTool` / 盾构选镐 | `player/auto-tool` | 重复且会抢槽。盾构挖**矿石**时本模块会把时运镐换到手上（石头仍用效率镐）。Meteor 只看快捷栏，且 `fortune-for-ores-and-crops` 默认关，关着时它会在开始破坏的瞬间把效率镐换回来。开着 Auto Tool 就必须把这项打开，Prefer 选 Fortune |
| `BorerTrail` 路点 | `render/waypoints` | 部分重复。本模块的路点绑定挖矿会话，暂时保留 |
| `PiglinBrawler.strafeDodge` | `combat/arrow-dodge` | 重复。已加 `brawlerStrafeDodge` 开关，开了 Meteor 的就把这个关掉 |

处理这些欠债时按第 1 节第 3 条办：加「交给 Meteor」开关，不要直接删功能。

### 4.2 有意做成配合（正面例子）

| twob2tkit | Meteor | 怎么配合 |
| --- | --- | --- |
| `PiglinBrawler` 近战 | `combat/kill-aura` | `brawlerMeleeEnabled=false` 时完全不碰近战和视角，只做 KillAura 不做的：反弹恶魂火球、拉弓射远处 |
| `PiglinBrawler` 火球 | `combat/arrow-dodge` | **躲和反弹互斥，见下方 4.3**。没开打猪人时保护页「恶魂防护」仍反弹/射恶魂，不飞开 |
| `KitController` 巡航 | `movement/flight` | 开始巡航就打开 Meteor 飞行；升空用跳键当飞升。没开飞就会在地上一直跳 |
| `NetherRoofAssist` | `movement/flight` | 同上 |
| 盾构挖掘 | `player/speed-mine`、`world/packet-mine`、`player/break-delay` | 走原版 `KeyMapping`。按镐、附魔、急迫、方块记住是点一下还是按住；没挖过的先试。Meteor 加速/把破坏间隔调成 0 仍可叠加 |
| 区域挖主动反击 | `combat/kill-aura`、`combat/bow-aimbot`、`combat/bow-spam` | 1.7.4 按苦力怕/射手/其它敌怪排序，复用 BowAim 地形弹道并自动拉弓放箭；反击期间临时协调原有三个模块，结束恢复。安全页可关自动反击。其它盾构模式继续原有防护 |
| 挖树遇铁傀儡 | `combat/kill-aura` | 铁傀儡不是 `Enemy`。KillAura 开着或傀儡在打你时停砍、切剑、飞到头顶，近战交给 KillAura。不要拿着剪刀继续砍叶 |
| 挖树选剪刀/斧 | `player/auto-tool` 的 `anti-break` | 快坏的工具（默认剩不到 10%）会被 Meteor 取消破坏并松左键。本模块不再选快坏的剪刀/斧，叶子改空手砍 |
| 挖树日志自检 | 无 | Meteor 没有。`LogReview` 扫 chopper.log，卡住问本机 Grok |
| 自动保护 | `combat/kill-aura`、`combat/auto-log` | 被怪物打了才用反射打开这两个模块。不自己挥剑、不自己断线。岩浆烫伤不开。默认开 |
| 盾构扔废石 | `misc/inventory-tweaks` 的 auto-drop | Meteor 会按名单一直扔，且默认朝准星方向。本模块只在主背包空格 ≤ 3 时扔废石，并先发朝后视角包再扔。圆石留 64，深板岩/深板岩圆石不留，其它封路石头每种留 16 |
| 区域挖卸货（1.7.7） | `misc/inventory-tweaks`、`player/auto-replenish` | 两个默认关闭的选项：快满时到区域外丢普通石料、自动放箱存产物。区域外至少 4 格，留封水石料至少 64 和煤至少 16（整叠保留）；不扔矿物、不存工具补给。卸货旅程临时暂停上述模块并阻止本工具箱自动补货，结束恢复。原地 auto-drop 不负责区域外路线，勿同时依赖两套丢弃规则 |

### 4.3 恶魂火球：躲 or 反弹，只能二选一

`combat/arrow-dodge` 默认只躲箭；勾上 `all-projectiles` 之后连恶魂火球一起躲。它的做法是每 tick
模拟弹道，只要预测路径离你不到 `distance-check`（默认 1 格）就**直接覆盖你的 `deltaMovement`**
把你推开，一直推到安全为止。火和灵魂火**没有碰撞箱**，`isValid` 只看碰撞，所以会被推进堡垒柱子上的火里。

而反弹火球要求你进到 3 格以内，也就是必须站在弹道上。两件事物理上互斥，**开了前者后者永远打不中**。

没开「自动打猪人」时，保护页的 **恶魂防护**（默认开）仍然反弹来火球；没在挖矿/巡航等其它自动动作时还会拉弓射恶魂。它不自己飞开、不拉高、不横移。盾构进行中只打断去反弹火球，不为远处恶魂抢镐。

推荐配置（互补，不冲突）：

| | Meteor `arrow-dodge` | twob2tkit |
| --- | --- | --- |
| **想反弹火球**（推荐） | 开启，`all-projectiles` **关** | 恶魂防护开，打猪人设置「恶魂火球：反弹」 |
| 想躲火球 | 开启，`all-projectiles` **开** | 「恶魂火球：不管，交给 Meteor 躲」，并关掉恶魂防护 |

第一种下弩猪的箭仍由 Meteor 躲，火球由本模块弹回去还给恶魂，各管一段。

另外反弹时本模块**任何情况下都不会横移**（自己横移同样会把自己挪出弹道），
瞄准也改成瞄恶魂本体而不是火球——原版是按攻击者的视线朝向弹出去的，瞄恶魂回弹才走直线。

### 4.4 弓瞄准：Meteor 只算角度，不判断能不能打到

`combat/bow-aimbot` 只做一件事：**你手动按住右键时**按抛物线公式算抬头角，然后转视角。它不自己拉弓、
不自己松手，也不检查那一箭会不会先撞到地形——目标蹲在坑里或者隔着墙时，它照样把你的头摆好让你空放。

所以 `PiglinBrawler` 自带 `BowAim`，在 Meteor 的基础上多做两件事：

1. **弹道模拟**：解出抬头角之后按原版箭的物理（初速 3 格/tick、阻力 0.99、重力 0.05）逐 tick 推进，
   沿途做方块裁剪。撞墙在命中之前就判定这枪打不出去，压根不拉弓，并把这个目标晾 60 tick 去找别的。
   解析解不含阻力会打短，所以按 0/1/2/3/4.5/6/8/11 度依次上抬重试。
2. **自动拉满再松手**，按 `brawlerBowChargeTicks`（默认 20）。

两边同时开会抢视角：本模块每 tick 用 `ChopperKeys.lookAt` 写朝向，`bow-aimbot` 在 `TickEvent.Pre` 里
也写一次。**开自动打猪人时把 `bow-aimbot` 关掉。**

### 4.5 悬停高度：Meteor 完全没有

`brawlerHoverHeight`（默认 3 格）是 twob2tkit 独有的。飞行刷猪人时如果站得不够高，拿矛的猪人
攻击距离比拿剑的长，会够到玩家。低于设定值时本模块按住空格往上顶（只在飞行时；走地面只在
状态栏提示，跳一下没用）。空格用的是和横移键一样的「只松自己按下那一次」写法，不会吃掉玩家手按的跳跃。

Meteor 的 `kill-aura` 只有 range，没有高度差概念；`anti-afk` 反而会乱按空格，见「常见坑」。

### 4.6 Meteor 没有，属于正当新增

- `TunnelBorer` 自动找矿盾构：Meteor 的 `excavator` 是挖固定选区，`vein-miner` 是连锁同种方块，
  `infinity-miner` 只管耐久，都不会自己找矿脉并规划隧道。瞄准默认只沿东西南北上下（轴向），可选任意方向。
  Meteor `excavator` 用 Baritone，只能在原版准星够得着的地方右键两点，不能填坐标。
  本模块 **区域挖**：两点对角（准星 128 格 / 下次左键 / 输入坐标 / 脚下 40×40），由盾构机按这块往下挖。
- `AutoChopper` 砍树：Meteor 没有找树、砍完补种的模块。
- `AutoPlanter` 种田（含成熟作物收成再种）：Meteor 没有 `auto-harvest`。`nuker` 能砸方块但不会认作物、补种。默认开「自动收成」；若要用 Meteor Nuker 收田，把这项关掉以免抢左键。
- `SeedScout` 种子破解 + `StructureLocator` 结构定位 + `StructureGuide` 指引：Meteor 只有 `stash-finder`
  扫已加载区块，不做种子级别的结构推算。
- `MachineBuilder` / `TechMachines` / `SchematicLoader` 生电机全息与摆放。
- `LocalRecipes` / `LocalAdvancementManager` 本地配方与进度。
- `SurvivalAlertMonitor` / `AdventureMonitor` 提醒类：Meteor 的 `auto-eat`、`auto-gap`、`auto-totem`、
  `auto-log` 是**自动处置**。本模块现在也有挂机下线（钓鱼/巡航时附近玩家、低血、钓鱼时被打中一次），
  死亡会记凶手和时间到 `combat.log`。Meteor auto-log 仍可并存；它默认只看血量，且 `only-trusted` 默认关。
- `AutoSurround`：和 `combat/surround` 名字像但目的不同——Meteor 是脚下放黑曜石防水晶爆炸，
  本模块是把人整个封进方块盒子里躲怪。**新增同类功能前务必确认这种「同名不同事」的情况。**
- `AutoFisher` 定点钓鱼：Meteor 的 `auto-fish` 会抛钩收钩，但不锁视角、满包也不存箱。钩子一偏就钓不到。
  本模块记下开始时的坐标和朝向并写回，满包后找附近箱子存完再走回钓点。可勾选「钩子交给 Meteor auto-fish」，关掉后自己抛收。
- twob2tkit **模块栏**（`ClickGuiScreen` + `ClickGuiPanelScreen`）：左侧菜单 + 右侧主内容（首页总览），
  **不是 HTML / 网页**。分类页左键开关、右键或「设置」打开密排设置窗。分页按钮模式仍在设置里可切回去。
