# 方块回收的延迟拾取确认

实机：渔夫柜台安装期间，屋顶木板的 collect_item 已返回已到达但拾取未确认，稍后真实背包增加一块，原掉落物消失。旧流程因此退出，临时施工口需要单独恢复。

block_recovery.pickup 现在仅对这条精确的已结算回执额外观察最多五秒；库存恰好增加一件且原 UUID 消失后，调用原有严格的 observe_unconfirmed_pickup_terminal，再检查两个不同时间的库存状态。不会再次派发 collect_item，也不将其它未知结果当成成功。没有增量、增量不符、原掉落物仍在或严格回执检查失败时保留未决记录。

验证：捆绑 Python 环境下 test_block_recovery 9 项、test_pickup_terminal_observation 29 项通过。新增测试包含延迟到账、库存无变化、增量过多、掉落物仍在、严格观察拒绝。当前保留施工控制器仍使用原先加载的实现；源码修复供下次正常切换 Python 控制器使用，无需重启 Minecraft。

本次实际柜台与屋顶恢复证据：work/village-trading-20261017/live-village-092/install-fisherman-barrel-1426-proof.json。木桶已安装，10 名职业区村民健康；新住户仍显示旧图书管理员职业，未声称渔夫交易验收完成。
