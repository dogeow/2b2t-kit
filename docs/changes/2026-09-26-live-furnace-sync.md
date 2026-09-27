# 实机熔炉槽位同步修复

日期：2026-09-26。

本轮解决两类实机数据差异：空物品堆的容量元数据被误用，以及连续向燃料槽右键时发生的服务器状态纠正。最终采用“先在玩家背包稳定槽拆出准确数量，再整批一次性投炉”的方案。**最终整批投炉方案尚待实机验证；以下测试通过不代表整批熔炼或星舰材料已经完成。**

## 已确认的实机证据

### 空槽 `max_stack=1`

宿主 `AutomationBridge.stack(ItemStack)` 将 `ItemStack.getMaxStackSize()` 直接写入 `max_stack`。实机空槽的形状是：

```json
{"item":"minecraft:air","count":0,"max_stack":1}
```

这描述空物品堆，不是该炉格、工作台格或箱子格只能容纳一个物品。旧 `place_cell` 使用目标空槽的 `max_stack` 检查待放入的 20 个原料，因而在投料之前拒绝操作。`storage.move_amount` 有同样的容量判断；`Client.transfer` 的空槽剩余空间计算还会把精确存取拆成一次一个。

现在统一使用 `destination_capacity(source, destination)`：空槽采用待放入物品的上限；非空槽保留已有物品的上限；缺失旧格式元数据时回退到来源上限。16 个一堆的物品仍保持 16 的限制，不统一放宽成 64。

### 燃料槽从观察到的 0 纠正为实际的 1

两次连续右键投煤的失败均有原生操作记录。第一次错误请求为 `materials-e9c6b8279773`，见：

`outputs/starship/work/goal-current/smelting-live-capacity-fixed-20260926/events.jsonl`

第二次错误请求为 `materials-85b24ad6dd38`，见：

`outputs/starship/work/goal-current/reconcile-partial-fuel-live/events.jsonl`

第二次并不是单纯的煤数量减少。失败请求和当时读取的原生回执对应如下：

| 字段 | 请求预期 | 原生错误回执中的实际状态 |
| --- | --- | --- |
| 菜单 | 37 | 37 |
| 燃料槽 | `air × 0` | `coal × 1` |
| 原料槽 | — | `cobblestone × 19` |
| 成品槽 | — | `air × 0` |
| 光标 | — | `coal × 47` |
| 结果 | — | `phase=error`, `detail=Slot item changed` |

原生回执时间为 `1790435132868`，读取位置为 `/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation/reply-materials-85b24ad6dd38.json`。旧成功回执已经被清理，因此没有把事件记录以外的完整前一帧状态当成已知事实。

代码确认 `Slot item changed` 和 `Slot count changed` 均在 `AutomationBridge` 的 `handleContainerInput` 调用之前抛出。这两种错误能证明该次点击没有派发，但不能证明目标变化一定属于自然燃烧。第二次实测是观察值 `0 → 1`，所以“只允许自然消耗”的保护拒绝正确，本次没有放宽成允许目标增加。

## 最终方案

`InventorySession.place_cell` 向炉输入或燃料槽放小批物料时：

1. 在玩家背包中找一个空槽，使用现有 `storage.move_amount` 精确暂存本次所需数量。
2. 核对来源数量、暂存数量和空光标。
3. 拿起暂存的准确小堆，一次左键投入炉格。
4. 保留原有库存变化、炉内输入与产出守恒、批次回执检查。

从 49 或 64 枚煤中投 3 枚需 7 次实际点击，投 4 枚需 8 次。拆分的单枚点击都发生在稳定玩家槽，不再连续右键动态燃料槽。暂存槽在完成后恢复为空。背包完全没有空槽时，使用较慢的来源槽余量返回路径，仍只向炉格投放一次，不覆盖现有物品。

`inventory_exact.take_exact` 只处理箱子/潜影盒菜单内的 1–16 个来源物品，不适用于炉菜单。本次复用现有库存事务组件，未另写一套快拆逻辑。

之前新增的严格预检拒绝处理仍保留：仅炉输入/燃料投放遇到上述精确错误时，可在确认同菜单、光标/来源/所有玩家库存不变、输入与产出守恒、燃料仅减少后重读并最多重新提交两次。未知错误、超时、未确认变化、数量增加、人工改动和其他容器操作都不重放。

## 验证范围

全部通过，未运行 Java、未安装产物、未发起游戏请求：

- `decision-runtime/check_offline.py`：172 项离线 Python 回归。
- `test_construction_materials`、`test_goal_workflow`：追加 11 项回归。
- 修复时针对库存、装炉、存取与配方的 68 项检查属于上述相关覆盖的补充执行，不与整套数量相加声称独立测试总数。
- `git diff --check`：通过。

覆盖空槽 `max_stack=1`、16 堆上限、精确半堆存取、自然燃烧与熔炼中的明确拒绝、来源/光标/菜单变化、未知回执不重放、观察值 `0 → 1` 必须停止、49/64 枚煤中暂存 3/4 枚、暂存槽回空及背包满时保护既有物品。

执行日志：

- `/tmp/kit-live-furnace-offline-20260926.log`
- `/tmp/kit-live-furnace-goal-20260926.log`

尚待验证：在新进程中实际执行准确小堆整批投炉，观察服务器最终库存和炉内状态；只有完成全量核对才能记录该批完成。已有的部分投料回执不能作为重新投料的授权或整批完成凭据。
