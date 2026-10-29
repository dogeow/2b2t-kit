# 外部投影打印模式交接

主包 `2026.10.29.7` 提供 `printer_mode_handoff_protocol=1`，让物资流程在不关闭防护、不模拟按键的情况下暂停/恢复用户开启的 Litematica Printer。

`printer_mode` 要求当前世界、控制版本、短期有效期、站点和选中投影 key 均匹配；当前没有物资/打印任务或其它控制器、没有施工批次、玩家健康且无界面、光标为空且无手动输入。调用参数包括布尔 `enabled`、当前布尔 `expected_enabled` 及最近快照中的整数 `expected_external_revision`。模式或版本已改变时拒绝操作。

暂停会清理尚未发送的外部打印队列，再允许独立物资租约接手。实际放置仍由原打印 Mod 完成；物资流程结束、检修口全部复原并释放租约后才能恢复外部模式。不会为了改模式停止全部功能、解除安全锁或改变物品栏。

`professional_printer.external_mode_revision` 与 `last_external_enabled` 记录观测到的外部模式变化。Kit 自己暂停、启用打印或结束打印的写入不算用户更改，同步配置回调也不算。恢复时须检查最新版本；用户中途作出的新选择优先于旧的恢复目标。
