# 存放后的重复仓库检查

本次存放已经完成，但本地地图补给编排在存放后无条件调用 `Backend.fetch`，又打开登记仓库及末影箱，没有取得额外目标材料。重复检查的原因是编排把背包整理和通用取料连在同一轮，并非存放失败或箱子位置未记录。

当前连接 `3f1f75ac-886c-4002-b544-669a132e1aac` 的实际回执确认：凝灰岩、石头、橡木木板、云杉木板、闪长岩各2个已经放入 `[761019,64,797852]`。`remaining_deposit` 为空，`complete=true`。樱花木板余19个；原木96、金苹果15、火把54、铁锭33仍随身携带。

本地编排 `work/live-20261004/warehouse-map-cargo-room-3f1f.py` 已移除存放后的无条件 `fetch`。该轮原始取料及存放回执均保留，没有重写成取料成功。现有存放资料已整理成 `current-known-storage-3f1f.json`，用于定位来源；需要真实转移时只访问所需材料的登记来源，并核验当前箱子和转移结果。记录不代替实时库存证明。

后续直接调用既有 Kit `scan_trees` / `chop` 采集用户种植的樱花树；背包合成等采集完整结束并验证原生停车后再开始。合成按实际容量限制，原木96根保留，不再触发通用仓库检查。本次未修改或部署 Kit 宿主、引擎或通用仓库模块。

证据：`work/live-20261004/warehouse-map-cargo-room-3f1f-003/actual-small-material-storage.json`、`actual-warehouse-fetch.json`、`progress.json`、`native-high-keep.json`；编排语法检查通过。完整地图及真实像素验收仍未完成。

原生两棵樱花树本轮新增74根原木，实际随身96→170，临时垫块0。离树直线上升被原生接口在派发前拒绝，回执明确已知且无未确认请求；沿用同一原任务，复用 `owned_air_escape.escape_side` 扫描侧移再升高，实际高空驻留通过。错误回执保留，另存恢复证明。后续本地树批次已复用此离树入口。证明：`user-planted-cherry-batch-3f1f-002/actual-collected-inventory-frames.json`、`treebatch002-known-side-finish-3f1f-001/escape/verified.json`、`native-high-keep.json`。

本轮木板合成实物19→275，原木170→106；既有原生投影施工新增265格，完整现场守恒与原生高空停车通过。对完整16384格图像及128格参考行的实际扫描复算为6754/16512，剩9758格。樱花木板剩312格，其中311格可正常施工、1格保留旧未知回执。证明：`map-treebatch002-carried-craft-3f1f-002/`、`map-treebatch002-followthrough-3f1f-002/full-final-scene-recount.json`、`stock-print/print-run/progress.json`。下一轮本地串行程序已开始，继续既有采集、合成、施工入口，无通用翻箱步骤。完整地图未完成。

下一轮在砍树前发现仅2个背包空位，五叠各2块木板占位。未开始砍树且已有精确导航完成回执；同一原任务通过既有库存转移接口合并为一叠10块，数量守恒，空位增至6。无需回仓库。随后同一任务继续原生砍树。证明：`treebatch003-capacity-chop-finish-3f1f-001/actual-backpack-compaction.json`。后续只读等待合成/打印编排保留，当前采集未冒充完成。

第三轮同任务合并余料后采集两棵樱花树，新收60根，实际原木106→166；按真实容量消耗61根，木板10→254，原木余105。新增246格正常施工与完整现场守恒、高空停车均通过。完整图像16384格及参考行128格扫描复算为7000/16512，剩9512格，樱花剩66格，其中65格普通施工、1格旧未知回执保留。证明：`treebatch003-capacity-chop-finish-3f1f-001/`、`map-treebatch003-carried-craft-3f1f-001/`、`map-treebatch003-followthrough-3f1f-001/full-final-scene-recount.json`。已启动只读等待接续的一棵树批次，含背包余料合并，不再回仓库。

旧房屋及屋外树木库存记录另与实际取走回执交叉核对：53橡木原木、7橡木木板、16云杉原木，以及屋顶箱73橡木原木、108橡木木板，均已被此前确认取走。它们不再作为可用旧库存指引重复查箱；目前库存仍不跨世界计入现货。证据 `map-known-depleted-sources-20261009.json` 绑定原取料双帧、源减少及背包增加回执。
