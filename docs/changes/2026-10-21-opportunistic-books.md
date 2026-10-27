# 顺带保留附魔与交易材料补充

用户最新范围：22种必需附魔不变；忠诚III、引雷I、激流III、爆炸保护IV、弹射物保护IV、节肢杀手V、快速装填III、穿透IV、多重射击I、海之眷顾III、饵钓III只在碰巧遇到最高等级时保留并交易锁定。缺少这些不阻止完成，必需完成后不继续追刷。较低等级不因此保留。

项目状态与交易所需求已同步；刷新保护默认阻止拆除这11种最高等级报价。新增工作流将顺带锁定存入 `locked_optional_trades`，不增加必需完成数量。已有历史记录未改写。

## 本轮实机证据

- `work/village-trading-20261017/live-village-121/optional-and-required-survey-1846-proof.json`：ES06无目标；WN06、WS03当前无职业，旧的忠诚III、节肢杀手V报价未重新确认，不计锁定。
- `work/village-trading-20261017/live-village-121/private-library-pilot-1847-proof.json`：打印4.31秒，重新认领职业等待120.09秒超时；无新增锁定。床、活塞、围挡及顶板已恢复；无未知待执行动作。延迟原因未证实。
- `work/village-trading-20261017/live-village-121/paper-lock-budget-1848-proof.json`：三笔卖纸完成，并逐笔重新打开服务器报价验证经验增加；绿宝石15→18、纸137→65。屋顶已恢复。

必需附魔仍10/22，剩12种。刷新保护7项测试、占用床唤醒2项测试通过。这不是交易中心全面完成证明。
