# 地图已登记补光火把校验

闪长岩批次已确认46格后，局部扫描在[761063,65,797748]发现Block{minecraft:torch}，旧模板一律拒绝图面Y64上方任何方块而停止。该坐标是此前6个明确登记补光点之一，实际下方Y64方块仍匹配模型。火把MapColor.NONE的26.1.2实测依据保留于原补光报告，没有拆除火把或更改图像模型。

新增可复用projection_scene_lights.registered_map_light，只接受调用者明确登记的位置、图面上方一格、实际普通站立火把、passable=true/solid=false/fluid=false/block_entity=false，以及实际底座完整匹配模型。未登记灯、其他高度或方块、缺失/错误/湿/容器底座、缺少安全字段仍拒绝。4项新回归及相关共14项测试通过，原失败扫描也通过实际数据复核。工作模板按这6个已登记位置调用该规则并保留重复扫描检查；未改宿主或引擎，不需重启。

原闪长岩停止回执不改为done，46格先同原租约正常升空并独立全图审计7518/16512。新4格既有原生打印完整现场守恒和高空KEEP通过。最终独立服务器全图审计7522/16512，模型哈希仍0d3e07d872842a87efc9b748df6ddc6e6976af164777638b836e401e713bc8da；本轮新增石头53、闪长岩50，剩8990格、23种材料。

证据：work/live-20261004/diorite46-known-light-high-audit-017f-001/audit-result.json、diorite4-known-lights-print-017f-001/print-run/progress.json、stone53-diorite50-independent-complete-audit-017f-001/current-projection.json。原停止记录、火把和所有旧未知回执保留。完整地图和16384真实地图像素仍未完成。
