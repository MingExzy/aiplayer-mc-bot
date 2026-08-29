# AIPlayer — 开发者文档

---

## 目录

1. [整体架构](#1-整体架构)
2. [目录结构与模块职责](#2-目录结构与模块职责)
3. [核心流程](#3-核心流程)
4. [工具系统](#4-工具系统)
5. [技能系统](#5-技能系统)
6. [FastAPI 通信](#6-fastapi-通信)
7. [Prompt 设计](#7-prompt-设计)
8. [配置与环境变量](#8-配置与环境变量)
9. [测试](#9-测试)
10. [演化记录](#10-演化记录)

---

## 1. 整体架构

```
游戏聊天 @botX
   │
   ▼
Control/（Node.js）                          Decision/（Python）              LLM API
────────────────────                        ──────────────────              ─────────
launcher.js（多 Bot 父进程）                   main.py（FastAPI 入口）         DeepSeek / 兼容服务
  └─ launcher.js --bot（单 Bot 子进程）        └─ server.py
       ├─ bot/index.js 聊天监听                 │   ├─ plan() 决策入口（普通 / 技能续行）
       │   ├─ collectStatus 状态采集            │   ├─ reflect() 失败反思
       │   ├─ requestPlan → /plan/{id}         │   └─ saveSkill() 技能生成保存
       │   ├─ executeActions 动作执行           ├─ LLMAgent.py（AsyncOpenAI + 重试 + 错误分类）
       │   └─ 敌怪监控 / 任务中断                ├─ skill_manager.py（技能索引 / 续行上下文）
       ├─ core/registry.js 工具注册中心          ├─ prompts/*.yaml（Jinja2 模板）
       ├─ tools/*.js 原子工具（22 个）          └─ LLMData.py（结构化输出模型）
       └─ python/client.js FastAPI 客户端
              │
              └────── FastAPI HTTP（:8000）──────┘
```

### 设计原则

- **LLM 只做决策，不做底层控制**：底层动作全部由 Mineflayer 工具执行
- **全量加载、一次输出**：22 个工具全部注入 prompt，LLM 直接输出动作序列，不需要分轮查询
- **N 步折中**：LLM 通过 `continue` 字段自选断点，兼顾实时反馈与多步依赖
- **结构化输出**：pydantic 模型 + `response_format` 约束 LLM 输出，保证可解析
- **跨进程通信**：Node 与 Python 之间只有 FastAPI HTTP 一个通道，状态采集由 Node 完成、随请求附带

---

## 2. 目录结构与模块职责

| 路径 | 职责 |
|---|---|
| `Control/launcher.js` | 多 Bot 启动器：`node launcher.js [N]` 启动 N 个子进程；`--bot` 为单 Bot 子进程模式；启动/退出时调用 `/register`、`/unregister`；终端快捷指令分发 |
| `Control/bot/index.js` | 创建 Mineflayer Bot（挂载 pathfinder）；监听 `@botX` 消息；规划→执行→续行主循环；敌怪监控与任务中断 |
| `Control/bot/history.js` | 进程内聊天历史 `{role, content, ts}`，上限 50 条 |
| `Control/core/registry.js` | 工具注册中心：扫描 `tools/`、目录监听热更新、同步 `tools.json`、运行时注册 |
| `Control/tools/*.js` | 22 个原子工具实现（一个工具一个文件） |
| `Control/actions/index.js` | `ExecuteAction` 注册中心分发、`TaskCompleteCheck` 状态收束、`SaveSkill` |
| `Control/python/client.js` | FastAPI 客户端：`collectStatus` / `requestPlan` / `executeActions` |
| `Control/commands/quick.js` | 终端快捷指令（`!背包`、`!保存技能`、`!注册工具`） |
| `Control/utils/plan-parse.js` | 规划响应解析：兼容 `actions` / `tool_calls` / `reply` 等形态 |
| `Control/config.json` | 本地配置：`fastapi_url`、`host`、`auto_status_tools`、`debug_mode` |
| `Decision/main.py` | FastAPI 应用：路由、全局 LLM 信号量、trace_id 中间件、异常兜底 |
| `Decision/server.py` | 业务逻辑：`init_server`、`plan`、`reflect`、`saveSkill`、tools.json mtime 热重载 |
| `Decision/LLMAgent.py` | LLM 客户端：AsyncOpenAI、重试装饰器、错误分类、LLM 日志 |
| `Decision/LLMData.py` | pydantic 输出模型：`LLMResponse` / `LLMReflect` / `LLMGenerateSkill` |
| `Decision/skill_manager.py` | 技能加载、索引、详情查询、续行上下文构建、保存 |
| `Decision/prompts/*.yaml` | `decide` / `reflect` / `generateSkill` 提示词模板 |
| `Decision/config.py` | pydantic-settings 配置，自动读取根目录 `.env` |

---

## 3. 核心流程

### 3.1 正常执行

```
玩家: "@bot1 帮我挖点钻石"
  ↓ bot/index.js on('chat')
  addToHistory('player', ...)
  ↓ while (keepPlanning)
  collectStatus()  → 自动执行 GetState / GetAroundBlocks，采集状态快照
  requestPlan()    → POST /plan/{BOT_ID}（chatHistory + status + skillprogress，60s 超时）
  ↓ server.plan()
  demand = chatHistory 最后一条；历史去尾；status 拼成「当前 Bot 状态」注入 prompt
  skill_progress 为空 → normal_plan（全量工具 + 已保存技能摘要）
  ↓ LLM 输出（结构化）
  {"actions": [...], "continue": true, "skillProgress": null}
  ↓ 返回 Node
  normalizeActionList() → executeActions() 逐条执行
  continue=true  → 写入「继续任务」，携带 skillProgress 进入下一轮 while
  continue=false → 任务完成，结束
```

### 3.2 失败反思

```
动作执行失败
  ↓
POST /reflect/{BOT_ID}（chatHistory + status，10s 超时）
  ↓ LLM 分析失败原因（failure / reason / label）
  ↓ 写入历史 "失败反思: ..."
  ↓ 结束本轮，等待玩家重新输入
```

### 3.3 技能续行

```
LLM 判断需求与已保存技能高度相关 → 输出 skillProgress {"name": "转圈", "next": 0}
  ↓ Node 端下一轮请求带上 skillprogress
  ↓ server.plan() 进入 excute_skill() 分支
  只把该子序列用到的工具注入 prompt
  ↓ LLM 严格按子序列输出，不得增删改
  非最后子序列 → 更新 skillProgress.next，continue=true
  最后子序列   → skillProgress=null，continue=false
```

### 3.4 多 Bot 与敌怪监控

- `node launcher.js N`：父进程 spawn N 个 `node launcher.js --bot` 子进程，环境变量 `BOT_ID = 1..N`，Bot 用户名为 `AIPlayer1..N`
- 游戏内消息必须以 `@botN` 开头；FastAPI 路由 `bot_id` 限制 `1..3`
- 终端快捷指令由父进程分发：不带 `@botN` 全部分发，`!xxx @bot2` 只发给 Bot2
- 敌怪监控：每 2s 扫描 16 格内敌对生物；发现后中断当前任务、向反方向逃离 30 格；连续 3 次安全扫描后解除中断，提示重新发送需求

---

## 4. 工具系统

### 4.1 工具文件格式

一个工具 = `Control/tools/` 目录下一个 `.js` 文件：

```js
module.exports = {
  name: "Move",
  args: ["direction", "blocks"],
  class: "BasicControlTools",
  description: "Move/walk/go in a direction...",
  async execute(bot, args) {
    // ...
    return { message: "..." }
  }
}
```

### 4.2 注册中心（core/registry.js）

- 启动时扫描 `tools/` 目录，把注册表作为工具的唯一来源，并同步生成 `tools.json`
- 目录监听：新增 / 修改 / 删除工具文件自动注册、更新、移除（300ms 防抖），无需重启
- Python 端按 `tools.json` 的 mtime 热重载，无需重启服务
- 加工具的三种方式：
  1. 直接往 `tools/` 放一个符合格式的 `.js` 文件
  2. 代码调用 `registry.register(toolDef)` / `registerFromFile(filePath)`
  3. 终端快捷指令 `!注册工具 <JSON 定义>`（含 `code` 字段，运行时生成工具文件）

### 4.3 当前工具清单（22 个）

| 类别 | 工具 | 说明 |
|---|---|---|
| 查询 | GetState, GetInventory, GetItemInHand, GetAroundEntities, GetAroundBlocks, GetAroundNearestTargetBlocks, GetRecipesForItem | Bot 状态 / 背包 / 周围环境 / 配方查询 |
| 基础控制 | Move, MoveTo, Jump, Sneak, run, Turn, LookAt | 移动与控制 |
| 物品 | EquipItemInHand, UseItemInHand, ThrowItems | 装备 / 使用 / 丢弃 |
| 方块交互 | PlaceBlock, BreakBlock | 放置 / 破坏 |
| 玩家交互 | Chat | 发消息 |
| 高级 | CraftItem, FollowPlayer | 合成 / 跟随 |

### 4.4 工具粒度原则

- **过低**（LLM 不该做）：Jump、run 这类单一动作 → 规则即可实现
- **合适**（LLM 该决策）：装备工具前先查背包 → EquipItemInHand → BreakBlock
- **过高**（规则更好）：建筑蓝图整体放置 → LLM 决策结构，规则执行放置

---

## 5. 技能系统

### 保存

```
终端: !保存技能 转圈
  → POST /saveSkill/{bot_id}?skill_name=转圈
  → generate_skill：LLM 从历史中提取工具名序列
  → 按查询工具拆分子序列，满 10 步截断
  → 存入 skills/{name}/skill.json，更新内存索引
```

### 匹配与执行

- 正常规划时，已保存技能的名称、描述、首个动作序列随 prompt 展示
- LLM 只在需求与技能**高度相关**时执行；闲聊、打招呼不触发技能
- 续行通过 `skillProgress {name, next}` 逐段推进，只展示当前子序列用到的工具

当前内置示例技能：`转圈`（`Decision/skills/转圈/skill.json`）。

---

## 6. FastAPI 通信

### 传输方式

FastAPI + HTTP JSON（uvicorn，端口 8000，Node 端地址见 `Control/config.json` 的 `fastapi_url`，可被环境变量 `FASTAPI_URL` 覆盖）。

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | launcher 启动时注册 Bot（携带 bot_id、pid） |
| POST | `/unregister` | Bot 退出时注销 |
| POST | `/plan/{bot_id}` | 请求下一轮动作规划（bot_id 1..3，Node 端 60s 超时） |
| POST | `/reflect/{bot_id}` | 任务失败反思 |
| POST | `/saveSkill/{bot_id}?skill_name=xxx` | 生成并保存技能 |
| GET | `/health` | 健康检查 |

### 请求体（ChatRequest）

```json
{
  "user": "player1",
  "chatHistory": [{"role": "player", "content": "帮我挖钻石", "ts": 1750000000}],
  "skillprogress": "null 或 {\"name\":\"转圈\",\"next\":0} 的 JSON 字符串",
  "status": {"GetState": "...", "GetAroundBlocks": "..."},
  "trace_id": "可选，日志追踪"
}
```

### 关键处理

- **全局信号量**：`GLOBAL_LLM_SEMAPHORE`（默认 10）限制并发 LLM 调用
- **trace_id**：HTTP 中间件生成 / 透传，贯穿 Node → FastAPI → LLM 日志，并在响应头回传
- **异常兜底**：任意异常返回 500，并附带一个 Chat 动作提示错误
- **工具热重载**：`plan()` 每次调用前检查 `tools.json` mtime，变更即重读
- **状态注入**：`status` 字段由 Node 端 `collectStatus()` 自动采集（`auto_status_tools` 配置），拼成「当前 Bot 状态」注入 prompt，避免重复查询

---

## 7. Prompt 设计

### 模板机制

`Decision/prompts/*.yaml` 定义模板与变量，`LLMAgent.py` 用 Jinja2 渲染，随后以结构化输出模型调用 LLM。

### decide.yaml 核心规则（R1–R9）

- R1 身份：LLM 是 AIPlayer 机器人；`role=bot` 是自身输出
- R2 任务：根据玩家或系统需求输出下一轮动作序列
- R3 工具合法性：工具名必须来自「可选工具列表」，禁止编造
- R4 技能续行：`skill_progress` 为 null 表示非续行；续行时必须严格按子序列输出，不得修改 / 跳过 / 添加
- R5 动作约束：查询类工具必须是最后一个动作且 `continue=true`；累计 10 个动作必须截断
- R6 Chat 包裹：非续行场景以 Chat 开头、Chat 结尾（查询截断除外）；Chat 内容须回应需求、使用中文
- R7 错误处理：错误由游戏系统处理，LLM 假定动作都能成功
- R8 数据时效性：实体 / 周围方块信息超过 15 秒不可靠，需重新查询；配方信息始终有效
- R9 状态自动附带：`GetState` / `GetAroundBlocks` 已由系统注入，除非玩家明确要求否则不要重复调用

### 结构化输出模型（LLMData.py）

```python
class LLMResponse(BaseModel):
    actions: list[Step]                    # Step = {name, args}
    continue_: bool                        # 序列化别名为 "continue"
    skillProgress: Optional[SkillProgress] # {name, next}

class LLMReflect(BaseModel):
    failure: str
    reason: str
    label: FailureLabel                    # 决策顺序 / 环境 / LLM 输出三类失败

class LLMGenerateSkill(BaseModel):
    name: str
    description: str
    action_sequences_length: int
    action_sequences: list[ActionSequence] # [{step, sub_action_seq}]
```

---

## 8. 配置与环境变量

### 根目录 `.env`（Decision/config.py 自动读取，docker-compose 的 decision 服务也加载）

| 变量 | 默认 | 说明 |
|---|---|---|
| `OpenAI_API_KEY` | 无（必填） | LLM API Key |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名 |
| `MODEL_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口地址 |
| `LLM_TEMPERATURE` | `0.7` | 采样温度 |
| `FASTAPI_URL` | `http://localhost:8000` | 决策服务地址（Node 端另有同名环境变量覆盖） |
| `GLOBAL_LLM_SEMAPHORE` | `10` | LLM 并发调用上限 |
| `LOG_LEVEL` | `info` | 日志级别 |

### Control/config.json

| 字段 | 默认 | 说明 |
|---|---|---|
| `fastapi_url` | `http://127.0.0.1:8000` | Node 端请求地址（可被环境变量 `FASTAPI_URL` 覆盖） |
| `debug_mode` | `false` | 调试模式 |
| `auto_status_tools` | `["GetState", "GetAroundBlocks"]` | 每轮规划前自动采集的状态工具 |
| `host` | `host.docker.internal` | Minecraft 服务器地址（本地运行改为 `127.0.0.1` 或局域网 IP） |

### 其他

- `BOT_ID`：单 Bot 子进程环境变量，决定 `@botN` 前缀与 `/plan/{bot_id}` 路径
- `FASTAPI_URL`：Node 端环境变量，优先于 `config.json`

---

## 9. 测试

`Control/test/` 为本地测试脚本（`.gitignore` 忽略 `test`，不随仓库提交）：

| 脚本 | 说明 |
|---|---|
| `node test/registry_test.js` | 工具注册机制自动化测试（无需启动游戏）：生成文件→注册→执行→tools.json 同步→热更新→删除清理 |
| `node test/registry_demo.js` | 用「假 Bot」演示注册→同步→执行→删除的完整链路，不启动 MC |
| `node test/testbot.js` | 直连本地 Minecraft 服务器的简易 Bot（固定版本 1.21.11） |

均在 `Control/` 目录下运行。

---

## 10. 演化记录

| 阶段 | 状态 | 说明 |
|---|---|---|
| 原子工具 + 全量加载 | ✅ 当前 | 22 个工具一次加载，LLM 直接输出 |
| N 步折中（continue） | ✅ 当前 | LLM 自选断点 |
| 技能系统 + skillProgress | ✅ 当前 | 保存 + 续行 |
| FastAPI 重构 | ✅ 当前 | MCP/SSE → FastAPI HTTP（plan/reflect/saveSkill） |
| 工具文件化 | ✅ 当前 | 22 个原子工具拆为 tools/ 独立文件，注册中心统一加载与热更新 |
| 环境状态注入 | ✅ 当前 | 每轮规划自动采集 GetState/GetAroundBlocks 注入 prompt（status 字段） |
| 结构化输出 | ✅ 当前 | pydantic 模型 + response_format（替代纯 JSON 解析） |
| 异步 LLM 调用 | ✅ 当前 | AsyncOpenAI |
| 敌怪监控 | ✅ 当前 | 敌对生物中断任务并逃离 |
| 多 Bot 启动器 | ✅ 当前 | launcher.js N，注册/注销自动上报 |
| Docker 化 | ✅ 当前 | docker-compose（control + decision），数据卷持久化 tools.json / skills |
| 关键词预选 + tool_queries | ❌ 移除 | 全量加载后不需要 |
| 嵌入模型匹配 | ❌ 移除 | 去掉 500MB 模型依赖 |
| 思考+执行分离 | ❌ 尝试后回退 | 增加复杂度但没有实质收益 |
| Agentic 经验回放 | ⏸ 暂缓 | 需要区分 LLM 错误和环境限制 |
