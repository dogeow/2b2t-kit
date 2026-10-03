# 本地空闲作业服务

这是显式启用的本地确定性脚本，不调用模型。轮换复用已登记土豆收田存箱、牛羊繁殖、烹饪存箱和已登记田块种植；不扩大田块或动物范围，不纳入未登记物资来源。牛羊保留数沿用农场配置，默认仍为20。

首次配置从已经存在的 `farm-caretaker-profile.json` 及原 registry 生成。小麦种植需要明确传入已经登记的 `farms/<key>/registry.json`，不会自动搜索新田块。

```sh
python idle_service_cli.py --caretaker-profile /absolute/farm-caretaker-profile.json init
python idle_service_cli.py status
python idle_service_cli.py run
python idle_service_cli.py pause
python idle_service_cli.py resume
python idle_service_cli.py stop
```

重启/手动重新连接后，只有原田块完成且所有plant/preparation/harvest都无未确认动作时，玩家可明确授权当前连接重新核对：

```sh
python idle_service_cli.py revalidate-fields --acknowledge-existing-fields
```

该命令不启动worker、不解锁或重连，只发送两次有界scan，逐格确认原登记farmland、相同作物(age0..7)和中心水源。旧registry/planting/preparation/harvest证据原字节归档，当前连接观察单独保存，再更新已完成记录的connection binding；旧动作回执、消耗数量、已完成数保持原值，明确标注这不是新播种/新开田回执。任何unknown或原格变化均拒绝。默认run/resume不会静默执行此恢复。

明确登记的小麦田通过共用收获内核检查真实age7/farmland，最多收4格，普通mining确认后分别核对wheat/seeds掉落和精确原格补种，保留至少4粒种子。实际小麦入包后可供牛羊喂养，不能把种子当小麦或猜产量。每田共享原preparation lock覆盖业务和cleanup，原harvest-active指向未决记录时阻断新out，不绕过旧pending。

`template` 仅输出未授权模板。`init` 保存配置，不启动服务。`run` 持有该服务器/维度唯一 worker flock。原 caretaker worker 也须退出；每个农场作业持有其原工作锁，但不会改写 caretaker 的周期记录。

只有当前世界、健康、食物、空光标和真实活动状态合格，角色静止且实际游戏移动输入连续安静至少5秒后才工作。前台同样可启动，不采样全局OS键鼠/HID，CmdTab和窗口焦点切换本身不会重置计时。实际WASD/移动、界面、材料、施工、挖矿、其它租约、保护和低血量锁仍优先。切换事件才写 events，持续轮询与心跳不刷日志。断线或换世界停止，脚本没有解锁和重连接口。

钓鱼默认关闭。启用需要 `fishing.shore` 的明确授权、近水坐标和视角。服务复用已有 `_travel` 在经过真实扫描的安全路线上接近指定岸边，正常 `walk(restore_flight=false)` 后使用现有owned-ground两帧400ms落地证明，再以正常air-only导航在同一已证明站位恢复Flight。每个原生navigate/walk保存原意图，未知结果不重发。不会自动寻找未登记地点。

最终两次真实扫描核对干燥支撑、头部空间、水源、稳定站位和投竿区域，宽容器范围的远处无害动物不会整体阻断；真实entity bounds与body/投竿段相交或近8格怪物才阻断。容器检查使用只读实际 `fisher_chest_range`，扫描仍保留至少8格危险范围。程序要求 `idle_fishing_protocol=1`，tagged idle fish原生模式禁止autoDeposit，满包在原生tick立即停止；该模式使用临时控制器字段，不改玩家偏好。启动回执和实际活动状态都须确认 `fisher_deposit_allowed=false`。必须实际携带耐久大于32的鱼竿并有至少8个空槽，Python看到余量少于4槽提前停；原生禁存箱是防竞态/新箱子的最终财物保护。接口只声明钓鱼控制启动/停止，没有把捕获次数当成入包证明。

原生fisher_start要求Flight，没有要求on_ground。恢复Flight后Minecraft可能报告on_ground=false；只接受先前精确owned-ground证明、原生精确停靠/恢复Flight证明以及同一姿势两次真实观察的完整链，不伪造地面标记。任何一环缺失都拒绝开钓。普通farm/feeding收尾仍返回已登记高空park，配置岸边后下一轮可自主再去钓鱼。

日常种植只允许已经登记且每次实际扫描仍是farmland的补种，绝不选择锄头耕普通草方块/泥土，不调用prepare扩地。显式新开田命令保留原功能。已完成记录的作物无确认地消失会阻断，不能假定可以重种；收获后的补种只在已证明的精确原田格执行。

种田与喂养继续使用原有单次交互及观察证明。牛羊喂养须实际携带至少2份小麦，缺料先等待，避免空闲作业盲目申请补料。未知种子、食物、箱子、炉子或原生请求保留原目录，服务停止自动工作；`resume` 不能清除或重播未知动作。

## 正式作业必须先取得优先权

正式 Python 材料控制者在创建 Client 之前调用：

```python
from idle_priority import request_foreground
priority = request_foreground(automation, 'materials-or-build', world_session)
try:
    # Create the normal formal Client and complete its work.
    ...
finally:
    priority.close()
```

或者使用 `idle_priority.foreground(...)` 上下文。请求维持有界心跳，先等空闲控制确实停止，才准入正式任务；退出后空闲服务重新等待安静和冷却。IdleJobClient 已设置 `idle_service_id` 属性且所有请求带该字段，正式 Client 钩子必须跳过它，避免递归抢占自己。

Kit host 的正式开始/手动输入入口也须优先停止与 `idle-service-owner.json` 精确匹配的旧 task/lease/world/revision，再允许新控制者。不得泛化停止其它作业。此文件有 owner 心跳和实际工作锁，不能把过期文件当成仍有权限。

原生 `status.json` 须提供 `idle_activity_protocol: 1`、`idle_activity: {busy: bool, conflicts: [string], idle_task_session: string}`。聚合所有真实按键、视角和背包控制者，包括现有单项状态没有暴露的辅助功能；`busy/conflicts` 排除精确当前 idle owner 本人的活动。缺元数据时服务停在 `WAIT_ACTIVITY_CAPABILITY`。这是必须由 host 接入的能力，不能用若干布尔全为false替代所有活动的证明。

构造时先保留当前已核对的高空parking目标。material_session的意图和确切envelope先落盘；失败或取消仍在请求中观察精确回复/租约，保持heartbeat，只有本scope释放、精确拒绝或原world结束后才能退出。正式正常收尾再使用原profile的停车点。

own revision更新后须等Host新帧明确返回本task且排除本输入，第一张时间较新的旧元数据快照不能结束等待。所有idle作业的navigate/walk复用现有规划器并记录逐请求意图；未知结果继续阻断。

2026-10-03实机已完成指定一格补种和原小麦田新连接只读复核，也验证material_session正常准入。完整空闲轮换尚未通过：一次导航元数据落后导致本输入安全释放，原cook_store/fetch阶段记录保留，服务未启用。钓鱼入包、小麦收获补种、牛羊喂养和正式token抢占都未实机验收。最新导航等待/全作业意图修正的128项组合测试通过，尚未安装这两项最新修正；见工作区outputs/idle-acceptance-20261003/handoff-summary.json。
