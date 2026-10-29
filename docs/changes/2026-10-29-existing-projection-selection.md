# 已有投影选择接口

`projection_registry_protocol=1` 提供已有图纸列表与切换，避免为往返施工重复导入。
原有导入数量限制不提高，不删除、合并或移动任何已有图纸。

`projection_list` 是只读操作，返回 `projection_registry`：

- `placements`：每项有 `index`、`fingerprint` 和原生 `placement` 元数据。
- `selected_index`：当前选择位置，无选择时为-1。
- `count`：已有数量，最多读取1024项。
- `registry_fingerprint`：包含列表顺序、各项内容、启用状态和选择位置的快照指纹。

指纹是原生接口返回的不透明令牌，调用方不能自行猜测或重新构造。
选择之前须用文件、原点、旋转、镜像、区域和名称核对目标。

`projection_select` 的专有参数为 `schema:1`、`manual_start:true`、
`placement_index`、`expected_registry`、`expected_fingerprint`。
同时携带现有的服务器、维度、人物位置、世界、修订号和过期时间字段。
只允许空闲、健康、无人工输入及安全锁、无其他动作/打印器持有者时操作，
渲染层必须已为ALL。快照或单项指纹不符时不做修改，重新只读观察。

成功仅改变已有图纸的全局启用状态和当前选择，返回 `projection_select`：
`success`、`placement_key`、`bounds`、`placement_count`、
`placements_added:0`、`placements_removed:0`、`world_blocks_changed:false`。
配置保存只报告已请求保存，不宣称Litematica磁盘保存成功。
原生控制修订号增加1。操作前后都有持久化选择日志。

部分失败恢复旧选择和启用状态；若期间出现图纸移动或注册列表变化，
不得以回滚覆盖后续编辑。无论切换成功与否都不会添加或删除图纸。
选择后必须通过 `projection_model` 重新核对完整原图哈希，再施工。
切换投影不代表真实方块或工程已经完成。
