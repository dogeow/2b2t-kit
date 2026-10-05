# Meteor Flight 的配置阶段退出兼容

宿主版本 `2026.10.5.2`；引擎 `1.7.81`、API 3 不变。此修复属于 Mixin，须在保留原工作记录后正常重启客户端一次才能加载，不能只热载引擎。本轮仅源码与离线校验，不部署或启动游戏。

2026-10-05 实际日志的 13:09:40 帧显示：`ClientboundStartConfigurationPacket` 触发 Meteor 的 `GameLeftEvent`，`Modules.onGameLeft` 调用 `Flight.onDeactivate`，随后在 `Flight.java:107` 因 `mc.player == null` 调用 `LocalPlayer.isSpectator()` 而抛出 NPE。13:09:41 显示网络协议错误。该记录是配置/网络生命周期问题，不是健康锁触发的退出；已完成取料及原未决施工记录不因源码修复升格或重放。

已核实际安装的 `meteor-client-26.1.2-42.jar`：SHA-256 `abd124d2d6b65b9cdc54fbf230d31817693386df0678f2953cfc97cfd3e1581f`，其 `fabric.mod.json` commit 为 `efb676db75f62853cf3e3c95af75d673839a0829`。安装 JAR 的 `javap -c -l -p` 显示 `onDeactivate()V` 在 bytecode 20、line 107 只有一次 `LocalPlayer.isSpectator()Z`，随后 line 108 调用 `abilitiesOff()`。相邻参考仓库的同一方法、配置阶段事件 hook 和 `Modules.onGameLeft` 与此对应；参考仓库未修改。

Kit 仅 Redirect `onDeactivate()V` 内这个确切调用。接收者为空时条件视作无需清理玩家 abilities，从而跳过该可选分支；存在玩家时调用原方法一次，原 spectator、survival、creative 清理分支保持。玩家尚在而 level/gameMode 已清除时仍允许合法 abilities 恢复，不套用要求整个世界存在的 tick 门。使用惰性 lambda，避免方法引用在检查前就解引用空接收者。

不取消整个 `onDeactivate`、`GameLeftEvent` 或模块取消订阅。没有伪造玩家、吞掉泛型异常、重连、解锁、安全锁或工作回执修改。`@Pseudo` 保持 Meteor 可选；`remap=false` 与明确 descriptor 对应已核 26.1.2-42 字节码；`require=0` 避免缺少可选类或变更后的调用位点阻止客户端启动。实际当前 JAR 的单一调用另由 ASM 测试校验；其他 Meteor 版本或其他模块的退出回调不由此保证。

纯测试覆盖空玩家不查询、正常条件与单次调用、缺世界时合法清理，以及不吞掉其他异常。接线测试核可选标记、精确调用目标、注册资源、无整方法取消和惰性原方法调用；本机安装 JAR 核对测试只读取字节码，不创建客户端。编译、包检查与这些测试不能代替重启后的实际配置切换验证，也不代表地图画或补光目标已完成。

捆绑 JDK 25 的 9 项针对检查和完整 `test jar verifyRuntimeEngineJar --offline` 通过，Java 共 1752 项，无失败、错误或跳过。主包 `twob2tkit-2026.10.5.2.jar` SHA256 为 `2f67d9607a96601ab40b3994b52bc0756601ccbf62757a344e169d0f53c33829`；独立引擎仍为已验证的 `16b9da95ddd817ecaf8e19897e4d98522f5e04da650d38ab915ccdf5cde28dfb`，未因本修复变化。安装和实机生效另行记录。
