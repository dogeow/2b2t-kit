# 橡木实采与退出后恢复

登记四棵自然橡木使用已有 Kit 固定树砍伐：背包实际0→17→22→28→33。前三棵原生完整收尾；第四棵原生已确认1棵、剩原木和垫块均0，但返回旁侧站位时碰撞停止，原始 stopped 回执保留，未称其为 done，未重复砍树。

外层异常结束后原心跳丢失，实机日志明确托管退出原因 heartbeat_lost / LOGOUT，未触发新的健康退出锁。按已有恢复授权正常重新连接，先进入服务器大厅，使用普通 Kit walk 和 interact_entity 一次交互 Join Queue NPC，回到原生存位置和33根原木，新世界连接017fb7fe-d7e5-4e7c-a8d6-a3e23e2961dc。

恢复后 Flight 关闭且站在围栏边。最初飞行侧移及整格围栏检查未找到出口，均未发送移动；改用原生普通 walk 对围栏实际碰撞形状完成0.53格侧移，再复用已有地面姿态证明和正常起飞，实际满血满饥饿、Flight开启、原木33不变及高空KEEP通过。围栏和动物未破坏。

在已确认高空按实际库存调用既有 Backend 合成，33根橡木→132块橡木木板，实际原木0、木板132。当前正常回地图进行完整服务器审计，之后串行调用已有原生地图打印器。旧世界、停止回执、失败扫描和旧只读等待记录均保留，不覆盖旧审计，不再通用翻箱。

证据：work/live-20261004/map-registered-oak-collect-craft-print-e0ff-002/、lobby-native-join-93a6-001/、oak33-reconnect-carried-craft-017f-001/known-native-ground-walk-ascent/、oak33-high-carried-craft-017f-001/。当前简洁续接状态current-continuation-20261010.json。整幅地图和真实地图像素仍未完成。
