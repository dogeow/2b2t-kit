# Kit 技能库 0.1

独立的 Voyager 风格技能层，接入现有 Minecraft Kit 的文件接口。无需更换游戏主包，不启动额外游戏角色，不修改主任务的事件监督器。仅使用 Python 标准库。

## 游戏内查看

技能库菜单入口：U → 生产 → 技能库。支持自动刷新、搜索、全部/已验证/候选筛选和技能详情。使用主包 1.9.21 或更新版本；本地技能记录器需单独启动。1.9.21 使用操作系统 HOME 定位共享目录，避免 HMCL 的 Java 用户目录覆盖导致列表为空。

记录器每两秒把显示目录写到 `~/.minecraft-kit/skills/catalog.json`；这是独立的只读展示数据，不是游戏动作信箱。目录包括所有技能的最新版本，不受检索前五项限制。

## 已实现

- 自动观察 `status.json`、`request.json` 和对应回复；记录执行前状态、请求和结束状态。记录器从不写游戏目录。
- 把可验证的采集原木、到点走位/飞行和当前站位打印交易转换成带参数的 Kit 技能。
- 真实背包数量、目标位置和服务器放置确认参与验收。`done`、AI 说“成功”、打印完几块都不能替代完整目标验收。
- 两次独立的原生成功记录才标记为 `verified`；重复记录不增加成功次数。修改技能会生成新版本，重新积累验证。
- AI 可通过 JSON 提交新技能候选；导入的历史/AI 经验不自动充当原生成功证据。
- 失败、人工接管、未完整观察到的动作保留为经验；人工接管不会被判成技能代码失败。
- 本地检索最多 5 个相关技能；准备目标规划上下文时技能内容最多 8000 字符。日常记录、检索和验收不调用模型，不消耗模型 Token。
- 可消费主任务事件监督器的 `events.jsonl`，使用独立读取游标，不改它的代码或数据。

## 和 Voyager 的关系

`kit_skills/library.py` 改编了 Voyager SkillManager 的版本保存、技能描述及限量检索结构。固定来源、完整 MIT 许可证和参考源码见 `kit_skills/vendor/voyager/`。本地检索替代 Chroma/远程嵌入，Kit 的声明式操作替代 Mineflayer JavaScript。没有安装整个 Voyager，也没有训练模型。

## 接入现有工作流

```sh
python3 install_observer.py
python3 skillctl.py inspect
python3 skillctl.py watch --seconds 30
python3 skillctl.py watch --events /实际监督器目录/events.jsonl
python3 skillctl.py status
python3 skillctl.py retrieve '采集原木'
python3 skillctl.py retrieve '打印投影' --candidates
python3 skillctl.py propose 新技能.json
python3 skillctl.py learn 执行经验.json
python3 skillctl.py compile collect_logs --parameters '{"item":"minecraft:oak_log","target_count":16,"seconds":60}'
```

`install_observer.py` 安装独立的 macOS 登录启动服务 `local.sam.minecraft.skill-memory`，自动读取 Kit 心跳及现有监督器的事件/诊断日志；只读游戏、不调用模型。

`watch` 不带秒数时持续观察；Ctrl+C 或向该观察器发送 SIGTERM 可停止。使用独立状态库和进程锁，不启动模型。

现有 AI/脚本可以调用：

```python
from kit_skills.library import SkillManager
from kit_skills.planning import goal_request, compile_plan
from kit_skills.learning import propose_from_ai, learn_episode

memory = SkillManager('/自己的持久目录/skills')
prompt = goal_request(memory, '采集原木', kit_current_state)
# 由现有监督器把 prompt 交给它选定的模型；本模块不创建新 agent。
# plan = existing_model(prompt)
# checked = compile_plan(memory, plan)
# 将 checked 的步骤交给现有 Kit 控制器执行，并逐步验证 verify_after。
```

规划结果必须固定技能版本，未解决的能力和未验证技能会阻止编译。编译只生成步骤，不操作角色。动作仍由现有 Kit 控制器统一执行；这个版本没有接管主任务的行动调度。

## 当前边界

这是可运行的技能记忆和学习接入层，不是完整的从零生存智能体。当前 Kit 接口没有高层“制作铁镐”等能力时，规划结果必须报告缺失，不能编造成功。

观察器只能验收自己完整看见的交易；过快被下一条请求覆盖、启动前已执行、没有原生回包或未获得执行前状态的动作只保存为经验。需要完整覆盖所有多步脚本时，在主控制器加入调用前/后的记录钩子。GUI 中的建造/混凝土等任务转换会记录为任务经验，后续可据此提出技能候选。

技能验证目前绑定所观察的 Kit 行为；新游戏版本、接口变化或新环境仍需复测。不会因一次“3 格打印成功”声明整栋房屋可完全自动建造。

## 检查

```sh
python3 -m unittest discover -v
```

测试使用隔离的临时文件和虚拟 Kit 回包，不控制当前游戏。实际连接验收使用只读 `inspect` 与短时 `watch`。
