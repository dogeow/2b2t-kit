# 原图平面水源修复

本次现场主机审计为5621/5825，含12个应为源水的格子仍是空气或流水。上层输送道分别使用短槽、弯道、漏斗与浮冰地板，固定西流8格或3×9源柱入口不适配。

2026.11.01.1新增显式 `projected_model_water_source`：目标必须是当前锁定原图的源水，当前只允许空气或普通流水；支撑必须是原图一致的干燥完整惰性方块。声明区域不超过4096格、同一水平面上下各一层，并检查额外邻接层的服务器区块与未退休预测。

每次准入以实际原版流体接收规则验证地板、边界和潜在流路；漏斗enabled和发射器triggered工作位可变化，朝向与材料必须一致。所有潜在新水格只能属于原图水域；缺地板、泥土堵塞、可能越界或源水再生进干半砖/原图流水会拒绝。不能用于新下落水道或气泡源，继续使用它们已有的专用入口。正常桶射线、实体检查、一次使用、双服务器回执、预测与库存守恒保持。

只有完整几何已验证、最近未受伤且没有移动投射物时，才可对远处不可见的普通敌对建立限定的非即时威胁证明：近敌、可见敌对、苦力怕、穿墙/未知类型仍拒绝；中立末影人还须未激怒且不可见。独立PvE、生命与人工接管保护仍优先。

`projected_model_water.place` 可热更新，计算原图连通水域与再生邻接边界，要求原生单次源水回执和完整流路三帧稳定。若只读发现目标已是源水，不发送桶操作，也不据此宣称完整水流已验证。

相关Java产物249项、Python入口及现有水操作16项通过。宿主入口需完整重启，worker只新增对应文件；实机纠正与原图流向仍须逐段验证，不将测试通过视为全塔完成。


## Live pre-send phase correction (2026.11.01.2)

The first live source request reported use_count=0, no packet observations, and no durable cell claim. The model-water check had interpreted a pre-send observation as post-placement. It now uses the same explicit-preflight/use-sent phase predicate as the existing column modes. A regression covers both phases; the isolated artifact passes 250 Java tests and changes only BucketWaterAction plus version metadata. This is not proof that any water has been placed.
