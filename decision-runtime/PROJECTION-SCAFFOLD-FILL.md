# 受限飞行 Scaffold 行

`projection_scaffold_fill_protocol=1` 是新的宿主和 Mixin 接口；安装新主包后需完整重启，不能只热加载引擎。

先停好其它工作，关闭 Meteor Scaffold，准备足够同一种材料的热栏库存，并在目标行附近保持健康的 PvE 材料租约。受限控制器独立借用实际 Meteor Flight 的 Velocity、速度、垂直比例、noSneak 和 Packet anti-kick；结束时逐项条件恢复，保持飞行和 PvE 防护。

先验证八格（含已放种子）再扩展整行：

```python
status = client.status()
result = client.request(
    'projection_scaffold_fill',
    placement_key=status['projection_selection']['key'],
    expected_item='minecraft:cobblestone',
    min=[761024, 64, 797631],
    max=[761031, 64, 797631],
    seconds=120,
)
```

整行改为 `max=[761151,64,797631]`、`seconds=300`。也可提供 `positions=[[x,y,z],...]`，须唯一、连续、同一 Y/Z、沿 X 排列，长度至多 128；控制器读取可接近的投影格，必须全部为同一种完整普通方块。初始角色须在该行 X 范围附近且距 Z 中线不超过两格；远距离接近另做，Scaffold 保持关闭。

配置租约将 Scaffold 限定到唯一材料白名单、air-place=true、radius=0、blocks-per-tick=1、auto-switch=true、rotate=false、fast-tower=false。第一层门禁在其 private `place` HEAD，早于自动换栏；实际 `gameMode.useItemOn` 前再次核对计算出的目标、真实手持材料和当前世界状态。该门禁只约束本次受控动作，不接管普通用户 Scaffold。

脚底目标高度是方块 Y+1.9，直接控制正常 Flight 输入；调高、调中线、危险、界面或外部接管时先关闭 owned Scaffold。逐帧检查身体碰撞和真实服务器区块，不走普通巡航、区域挖飞行或自动升高避障。最多两个待确认目标，每格只发送一次；库存按全局 `inventory_start-inventory_now == new_sent` 验证同种材料，不虚构单格库存分摊。仅在待确认窗口中允许服务器库存暂时落后，累计消耗必须介于已确认数与已发送数之间，差额不得超过当前待确认数。此时关闭 owned Scaffold 并停止移动和新发送；库存恢复到精确差值、所有待确认格收到匹配服务器更新，并稳定八 tick 后才继续。每格从首次发送起最多等待 100 tick；已确认库存回滚、超额消耗、未知或被修正的世界状态立即停止，不重发失败格。

完成要求全部行格实际匹配：原有格计入 `baseline_matched` 并持续核对，新格均收到当前连接匹配服务器更新、仍保持正确，并等八 tick；待确认数必须为零，累计库存必须精确。终态 `projection_scaffold_fill`（持续快照为 `last_projection_scaffold_fill`）包含行范围、baseline、新发送/确认、pending、累计库存、`inventory_sync_pending`、真实位置变化 `real_y_step/real_horizontal_step` 及 `raw_velocity`。原始 Y 速度中的 −0.0784 不代表实际位置下降，必须核实真实位移。

物理右键会先取消该 owned row，再允许用户的第一次原版交互；不会吞点击。设置或模块后来被用户改变时不覆盖；Module.toggle 观察器也识别 OFF→ON 的外部往返。异常关闭模块未确认时保留候选门禁和窄配置；防护正在撤离时延期恢复 Flight，避免覆盖逃离动作。

离线测试只能证明规则、门禁结构与资源账目。八格实战必须核实 Y64/Z797631、服务器确认数、累计材料差值、HP 和停靠位移后，才能运行 128 格。Scaffold 不负责 30 色画面的无差别铺设。
