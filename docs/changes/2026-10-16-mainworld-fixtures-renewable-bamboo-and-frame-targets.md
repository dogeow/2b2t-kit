# 主世界原图收尾、竹子留种与墙面展示框

晴庭原图仍缺石英时，不能把所有剩余摆件都当成石英依赖。花盆旁已有玻璃或墙面的七处位置，可以正常点击实际侧面放置和填充。`projection_potted_plants` 现在扫描实际邻接面，通过现有投影打印机放置，仍分别核对花盆、植物库存和最终方块；没有把玻璃、脚手架或空气伪造成实心地板。

实机已完成七个原图盆栽、一格脚手架和两根淡灰蜡烛，主体由 2813/2880 增至 2823/2880。新竹子带回后，在现有蕨苗圃的实际空位种了两株母竹，只采母竹上方；三份骨粉扩繁后得到八个随身竹子，用六个合成脚手架，保留两株母竹和两个随身繁殖材料。采蜂采用当前成熟的野生蜂巢、真实短烟柱和石板遮挡；已取得三个蜂脾并确认篝火熄灭，蜂巢保留。

普通整数拾取可能够不到竹竿旁的合并掉落；拾取目标也可能在导航期间继续下落。`drop_collection` 保留原拒绝/到达回执，对当前同一掉落实体使用已有空气通道或一次微小原生真实碰撞移动，核对库存增加和原实体消失，不重发未知拾取或攻击。第一批十六个竹子未及时拾回，不计为库存；后续新生竹段实际入包、返家和留种均有独立证据。

打开的门板占据门格一侧，门格中心不是门洞中心。`door_access.fly_open_door` 按实际门板厚度调整开口中心，先校准高度和横向位置，再短段通过；原生 `air_only` 持续检查真实碰撞，结束后恢复原门状态。旧地面路线不能处理部分地面时，不拆门和墙。玻璃隔断仍走完整扫描得到的既有空气路线。

Kit 2026.10.16.3 的 `BlockFaceTarget` 保留面中心优先，在中心被按钮遮挡时补查同一真实表面的内部采样点。每个点仍须命中原方块和要求的面。两个白旗展示框已正常放置，内容与四次旋转均按原图核验。引擎 1.8.5 增加独立的当前已加载服务器实体发光鱿鱼观测，保留普通鱿鱼旧协议，观察会包含移动后离开发生高度的真实发光鱿鱼。

完整 Java 检查通过 2002 项，相关 Python 回归按改动分组通过；安装过程备份旧主包、引擎和工作器并核对哈希。一次游戏连接超时并出现包解码错误，断线前生命值 20，无新的健康保护退出；旧世界未完成移动意图和回执独立保留，正常退出应用补丁后，重新核对新会话实际位置、健康和库存，没有重放旧动作或解除安全锁。

实机主要证据：

- `work/upgrade-26.2-642/overworld-ripe-honey-and-return-002/one-preserved-wild-nest-harvest/honeycomb.json`
- `work/upgrade-26.2-642/overworld-ripe-honey-and-return-003/actual-bamboo-parents.json`
- `work/upgrade-26.2-642/overworld-ripe-honey-and-return-003/owned-bamboo-for-scaffolding/nursery-production.json`
- `work/upgrade-26.2-642/villa-mainworld-scaffolding-candles-pots-001/physical-progress.json`
- `work/upgrade-26.2-642/villa-upper-candles-and-hot-glow-survey-003/control/after.json`
- `work/upgrade-26.2-642/host16-3-glow1-8-5-offline-install-001/installed-and-verified.json`
- `work/upgrade-26.2-642/fresh-network-reentry-host16-3-verified-001/fresh-actual-world-and-stock.json`
- `work/upgrade-26.2-642/villa-two-white-banner-frames-after-face-patch-002/complete.json`

整体验收尚未完成：原图还缺九个荧光展示框及一处依赖石英的地面展示框，主体余五十四格石英构件、两盏吊灯和一格地毯。荧光墨囊目前实际持有一个，继续按真实洞穴和实体补料。
