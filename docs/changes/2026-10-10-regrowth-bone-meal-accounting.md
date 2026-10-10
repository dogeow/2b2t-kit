# 树木长成时的骨粉扣减统计

实机催熟日志出现最后一次正常骨粉交互后，树根及上一格已是原木、背包同时减少1，但记录 `consumed=false`，总骨粉消耗也漏掉这一次。原因是生长扫描返回时仍沿用扫描前的背包快照，且长成分支在累加消耗之前返回。

现在扫描之后读取新的背包快照，将每次实际减少数量计入消耗总数，包括让树最终长成的交互。长成仍要求原种植格与正上方同树种树干，不把邻树叶或日志当作长成。未确认消耗或效果时仍不重复点击。

新增回归模拟交互回执先返回、骨粉扣减和树干变化在随后加载扫描中到达的时序；确认单次交互、总消耗1、生长记录消耗1、库存6→5。树木催熟、材料采集、空资源别名、木材流水线共101项通过，差异检查通过。

实机旧日志原件保留：`work/live-20261004/map-current-registered-root-charcoal80-af3b-002/cycle-00-existing-regrowth.json`、`map-grown-oak-same-owner-native-harvest-fuel-af3b-001/cycle-01-actual-regrowth.json`。本说明记录源码修正与离线测试；安装及修正后的新实机周期需另行核对，不修改运行中旧模块的已产生记录。

安装实机证据：已安装工人 `material_jobs/acquisition.py` 的 SHA256 为 `e50551009e4939d4c5a3eaa1d90f8500cc9540d5a3810ead0ead8c56df8d50f6`，清单其它字段保持，未重启。新周期 `map-current-planted-roots-charcoal80-af3b-001/cycle-00-existing-regrowth.json` 实际骨粉20→19、一次交互、消耗总数1、生长记录消耗1，复用原树苗 `planted_count=0`，随后固定树实际采到5个原木。旧记录未改写。
