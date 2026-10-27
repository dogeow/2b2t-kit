# 附魔报价复核与柜内打印实测

本轮最高等级附魔仍为10/22种，没有新增目标。对23个未锁定柜位进行了检查，取得15份当前服务器报价；另有3柜未放讲台、5柜唤醒后20秒内未认领职业。已取消的附魔和低于目标等级的报价均未购买。

ES06已完成两次正常挖回讲台与柜内投影打印。第一次原生打印及确认约2.5秒，第二次含准备与物理核验的放置约4.2秒。第一次打印后，重新认领职业约等了41.8秒；第二次等待120秒仍未认领。因此，柜内打印可行，但尚未证明职业认领能够稳定提速。已观察到的后续报价为饵钓Ⅱ、消失诅咒Ⅰ，均非目标。

渔夫和屠夫的柜位扩建后，安装检查仍使用旧边界，曾在打印请求发出前拦住操作。已重新扫描两处围挡、顶板、地板、床和实际村民边界，只把这两个已有居民的后侧边界增加一格，其他居民分配保持一致。可复用校验与策略更新位于 `decision-runtime/village_refit_bounds.py`；12项相关测试通过，并以本次真实完整扫描做了离线回放核验。

一次临时收床的掉落物未及时收回，原床不计作已回收。已取库存备用床放回ES06原位，并记录一张原床未回收。最后检查确认：讲台存在，床两部分存在，临时顶板均封回，活板门恢复原状态，活塞关闭，打印掩码关闭，无未确认原生请求，玩家及当前加载的受保护村民生命值正常。

整项任务继续保持未完成：还缺12种最高等级附魔，其余11种普通职业的补货仍须逐一实测。

## 证据

- [本轮最终安全检查](../../work/village-trading-20261017/live-village-121/library-checkpoint-1842-proof.json)
- [23柜报价复核](../../work/village-trading-20261017/live-village-121/library-max-survey-1833-proof.json)
- [柜内打印成功](../../work/village-trading-20261017/live-village-121/private-library-pilot-1836-proof.json)
- [连续试验与职业等待超时](../../work/village-trading-20261017/live-village-121/private-library-pilot-1837-proof.json)
- [围挡实测与边界同步](../../work/village-trading-20261017/live-village-121/sync-refit-containment-1835-proof.json)
- [备用床恢复、活塞复位](../../work/village-trading-20261017/live-village-121/private-library-pilot-1840-proof.json)
