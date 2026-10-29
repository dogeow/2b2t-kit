# 按原图排干含水半砖和活板门

`projected_waterlog_drain_protocol=1` 扩展 `bucket_fill`，普通取水行为保持不变。
只有显式参数 `projected_waterlog_drain:true` 才能进入该分支，同时需要
当前锁定 `placement_key` 和完整 `expected_dry_state`。原有 `pos`、
`expected_state`、`expected_hand`、世界/修订/持有者及过期字段仍须提供。

原图目标必须是干燥的单半砖或活板门；现场状态只允许水标志不同，
类型、方向、半层、开闭、电力等属性必须完全一致。排除双半砖、容器、
流动水、岩浆及普通方块。不能用此接口顺便校正朝向、改变半砖形态，
也不能排干原图要求含水的方块。

仍只发送一次正常空桶使用，不破坏方块。确认要求当前连接目标方块的
服务器更新精确等于原图干燥状态，以及选中桶槽独立服务器确认，空桶-1、
水桶+1、其余库存不变，且原生预测结束后稳定八拍。旋转排队期间允许
原含水状态存在，不将排队误认为已排干。若随后补水或状态变化，旧干燥
回执不能证明当前成功；保留持久化用桶记录，不自动再取一次。

回执 `bucket_water.projected_waterlog_drain`、`expected_dry_state` 和
`source_effect=waterlogged_block_drained` 说明该分支。是否完成仍以
`confirmed`、`unknown_outcome`、服务器回执与新投影审计为准。
邻水可能补回，单次排水成功也不能代替整片结构的后续检查。
