# 晴庭 Y63 干铺命令行入口

`projection_dry_paving_cli.py` 是一条独立的材料会话入口。它只处理 `projection_dry_paving.py` 中固定的 79 个冲突坐标和当前选中的八分区完整庭院投影。每批先取得新鲜的完整模型与 3701 格审计，再从仍符合原始方块、干燥邻域和保护缓冲区条件的坐标中选至多 4 格；没有随身替换方块的未动工格会跳过，同批也不会预留超过背包数量的方块。选格时对将要尝试的未动工格做原有严格几何检查所需的 3×4×3 只读局部扫描；栏杆等邻接障碍会跳过并将格子、原因写入 `selection.geometry_skips`，扫描本身失败则停止。既有未决日志和已完工却再度不符的格子仍会先阻止新动作；已回收掉落物的格子不会被此筛选跳过。真正的挖掘、掉落回收和放置都由 `pave_batch` 逐格再次核验。命令不调用 Jev，也不通过页面、鼠标脚本或玩家指令选格。

此入口已完成严格限定格子的实机试跑；后续仍应按现场审计和逐格日志推进。运行前必须已有相应的 Kit 主包、`dry_paving_protocol=2`、当前八分区投影、PvE 防护和材料背包。原生挖掘和放置只有在回包包含同一目标格的服务端方块更新确认后才会推进逐格日志。它不会安装主包或切换投影。

```bash
PY="$HOME/Library/Application Support/MinecraftDecisions/venv/bin/python"
"$PY" decision-runtime/projection_dry_paving_cli.py \
  --root /Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation \
  --park-high 761020.5 100 797854.5 \
  --minutes 1 --max-cells 1 --batch-size 1 --cell 760984 63 797828 \
  --out /path/to/new/dry-paving-run
```

默认工作时限为 20 分钟，可设 1–60 分钟；`--max-cells` 必须明确给出本次最多完成的 1–79 格。单格验收还必须用 `--cell X Y Z` 指定一个已核对坐标，不会自行挑最近的一格。多格运行可以重复 `--cell` 限定候选坐标，也可以在明确给出 `--max-cells` 后从固定 79 格清单的新审计中自动挑选。`--batch-size` 为每批 1–4 格，默认 4。时间限制用于决定是否发起下一批；已发出的原生动作及安全收尾会等待明确结果，因此总运行时间可能超过设定分钟数。程序不会在一格挖到一半时强行中断。`--out` 必须是新目录或空目录，避免旧高空确认或旧进度被误认为本次结果。`--root` 必须明确指定当前 Kit 自动化目录。

一次挖掘留下 `mine_intent` 时，可用 `--reconcile-evidence /path/to/proof.json` 对**同一个明确坐标**做单格恢复。它只接受 `--max-cells 1` 和一个 `--cell`。证明文件须包含原运行的完整 `events`、挖掘前后 `before_reply` / `after_reply`，以及精确 UUID 的 `pickup` 回执；若原掉落已无法收回，必须明确写入 `"accept_one_original_drop_loss": true`。旧版挖掘没有服务端更新回执时，恢复要求重新进入服务器后的新 `world_session`、两次完整已加载投影审计、目标格为空气且下方为干燥支撑、角色抵近后的实体范围内没有原掉落、原材料数量未增加。它把未收回的一块草方块记为 `drop_lost`，随后仍由普通单格流程确认一次放置；不会再次挖掘，也不会把损失记成已拾取。任何证据不符都保留原 `mine_intent`，继续阻止新格动作。

```bash
"$PY" decision-runtime/projection_dry_paving_cli.py \
  --root /Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation \
  --park-high 760994.5 110 797865.5 \
  --minutes 20 --max-cells 1 --batch-size 1 --cell 760995 63 797829 \
  --reconcile-evidence /path/to/reconciliation-evidence.json \
  --out /path/to/new/reconciliation-run
```

高空停靠点必须位于庭院投影上方至少 25 格、当前角色水平距离 32 格以内。材料会话建立后会再次检查角色位置，并重新扫描该停靠柱，核验至少 20 格净空；若这一步失败，不开始铺设并请求安全登出。结束后以本次 `stock-safety.json` 的 `KEEP_PVE_GUARD` 回执及实时保护状态确认为成功；若不能确认，命令返回非零退出码，并在结果中明确写出收尾未确认或安全登出请求。

每次运行写出 `progress.json` 与 `events.jsonl`；每完成一格就立即写入一次审计回执和真实已完成数量，后续格失败也保留这些进度。记录包含终态、批次前后完整审计摘要、每格坐标、目标/原始方块、完整格日志路径和审计回执。逐格不可重放日志保存在 Kit 自动化目录的 `dry-paving-v1/` 下。`pending_review` 表示曾发出动作但结果或意图不能安全重放，应检查对应格日志和现场；`manual_handoff` 表示用户已接管，不继续发命令。`materials_exhausted` 表示当前符合审计的格子都缺少随身替换方块，未发出新方块动作；`no_eligible_cells` 表示当前审计下没有仍可安全处理的白名单格。这些都不等于整个庭院投影完成。`completed` 只表示本次设定的新增格数已由日志与新审计确认。

离线回归命令：

```bash
cd /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime
"$HOME/Library/Application Support/MinecraftDecisions/venv/bin/python" \
  -m unittest -v test_projection_dry_paving_cli test_projection_dry_paving
```

该测试只使用临时目录和模拟回包，不连接游戏。实机前还需确认实际主包版本、游戏会话和高空停靠位置；离线测试不能替代这些现场条件。
