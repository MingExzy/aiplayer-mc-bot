# AIPlayer — Minecraft AI 玩家

一个基于 **LLM + MCP 协议** 的 Minecraft 自动玩家。玩家在游戏中打字下达指令，机器人自主规划并执行动作。

---

## 目录

1. [整体架构](#1-整体架构)
2. [MCP 协议实现详解](#2-mcp-协议实现详解)
3. [核心数据流](#3-核心数据流)
4. [两层筛选机制](#4-两层筛选机制)
5. [LLM 提示词设计](#5-llm-提示词设计)
6. [技能系统 (Skill)](#6-技能系统-skill)
7. [项目文件清单](#7-项目文件清单)
8. [数据来源](#8-数据来源)
9. [部署与运行](#9-部署与运行)

---

## 1. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        Node.js 进程                                 │
│                                                                    │
│   MainLoop.js (入口)                                                │
│       │                                                            │
│       ▼                                                            │
│   Bot.js (Mineflayer 客户端)                                        │
│       │  ● on('chat') 监听玩家聊天                                   │
│       │  ● on('spawn') 初始化 MCP 会话                               │
│       │  ● on('error'/'end') 自动重连                                │
│       │                                                            │
│       ▼                                                            │
│   MCP.js (MCP 客户端层)                                             │
│       │  ● initMCPSession() — 建立与 Python MCP Server 的会话        │
│       │  ● requestTaskPlan() — 调用 Python 端的 plan 接口            │
│       │  ● handleMessage() — 逐一执行 LLM 返回的动作序列              │
│       │                                                            │
│       ▼                                                            │
│   BotTools.js (工具执行层)                                           │
│       │  19 个工具的 ExecuteAction() 实现                            │
│       │  Move / BreakBlock / CraftItem / FollowPlayer ...           │
│       │                                                            │
│       ▼                                                            │
│   History.js — 环形缓冲区聊天历史 (50 条)                             │
└────────────────────────────────────────────────────────────────────┘
        │  ▲
        │  │ JSON-RPC over HTTP/SSE (MCP 协议)
        │  │
        ▼  │
┌────────────────────────────────────────────────────────────────────┐
│                        Python 进程                                  │
│                                                                    │
│   server_of_mcp.py (FastMCP Server)                                │
│       │  仅暴露一个 tools/call:  plan()                             │
│       │                                                            │
│       ├─ plan() 编排流程                                            │
│       │   ① 短路检测：玩家是否在请求"保存技能"                        │
│       │   ② 物品上下文构建 (item_query.py)                           │
│       │   ③ 技能上下文构建 (skill_manager.py)                        │
│       │   ④ 工具筛选 (filter_tools + keyword_matcher.py)            │
│       │   ⑤ LLM 决策 (LLMAgent.py → DeepSeek API)                  │
│       │   ⑥ 缓存动作序列供下次保存技能                                │
│       │                                                            │
│   item_query.py     ← 物品知识库 (items.json 加载 + 索引)            │
│   skill_manager.py  ← 技能管理 (加载/匹配/保存)                      │
│   keyword_matcher.py← 中文关键词 → MCP 工具映射                       │
│   item_name_map.py  ← 中文 → 英文物品名映射                          │
│   LLMAgent.py       ← LLM 调用 + 系统提示词                          │
└────────────────────────────────────────────────────────────────────┘
```

### 核心设计原则：One-Shot Planning

LLM **不直接调用 MCP 工具**。Node.js 是 MCP 的调用方，LLM 藏在 Python 进程中。

```
Node.js → call plan() once → Python 内部调 LLM → 返回完整动作序列 JSON
                                                              ↓
Node.js 逐条执行: Move → BreakBlock → Chat → ...
                                                              ↓
失败时系统捕获错误，写入聊天历史 → 下一轮 plan() 自动修正
```

这与"LLM 作为 MCP Client 自主编排工具"的模式不同。选择 One-Shot 的原因是：

| 因素 | One-Shot | LLM 自主编排 |
|---|---|---|
| 延迟 | 1 次 LLM 调用 ≈ 2-3s | N 步 × 2-3s，5 步 ≈ 15s |
| 错误处理 | 系统兜底 + 下一轮修正 | LLM 实时看到每步结果 |
| 复杂度 | 低 | 高（需 MCP Client + 推理循环） |
| MC 场景匹配 | ✅ 玩家更在乎响应速度 | ❌ 慢到不可用 |

---

## 2. MCP 协议实现详解

### 2.1 传输层

**Python Server** 使用 `fastmcp.FastMCP`，通过 `streamable-http` 传输：

```python
mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
```

**Node.js Client** 使用原生 `fetch`：

```
GET  /mcp         → 建立会话，获取 Mcp-Session-Id
POST /mcp         → 发送 JSON-RPC 请求，接收 SSE (Server-Sent Events)
```

### 2.2 会话生命周期

```
Node.js                           Python
  │                                 │
  │  GET /mcp                       │
  │◄── Mcp-Session-Id: xxx ─────    │
  │                                 │
  │  POST /mcp (initialize)         │
  │◄── SSE data: {...} ──────────    │
  │                                 │
  │  POST /mcp (tools/call plan)    │
  │◄── SSE data: {"result": ...} ──  │
  │                                 │
  │  ... (同一 session 继续通信)      │
```

### 2.3 JSON-RPC 格式

请求：

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "plan",
    "arguments": {
      "chatHistory": [{"role": "player", "content": "..."}, ...],
      "tools": [{"name": "Chat", "args": ["message"], ...}, ...]
    }
  },
  "id": 1
}
```

响应（SSE 格式）：

```
data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\"actions\":[...]}"}]}}
```

### 2.4 唯一对外接口

整个 Python 端只暴露一个 MCP tool：**`plan(chatHistory, tools)`**

```python
@mcp.tool()
def plan(chatHistory, tools):
    # 返回: {"actions": [{"name": "Move", "args": {"direction": "forward", "blocks": 5}}, ...]}
```

过去曾注册过 `query_item` 和 `SkillGenerate` 作为 MCP tool，但设计上 LLM 不直接调 MCP，所以全部改为内部函数，不再对外暴露。

---

## 3. 核心数据流

### 3.1 玩家发言 → Bot 执行

```
玩家: "帮我挖点钻石"
        │
Bot.js on('chat')
        │
        ▼
addToHistory("player", "帮我挖点钻石")
        │
        ▼
requestTaskPlan() ────────────────────────────┐
        │                                      │
        ▼                                      ▼
MCP.js: POST /mcp (tools/call plan)     Python plan()
        │                                      │
        │                                      ├─ 短路检查（保存技能？）
        │                                      ├─ build_item_context("钻石")
        │                                      │    → 查到 diamond, stack_size=64
        │                                      ├─ build_skill_context("钻石")
        │                                      │    → 匹配到技能「挖钻石」？
        │                                      ├─ filter_tools()
        │                                      │    → 关键词 "挖" → BreakBlock
        │                                      │    → 嵌入补充 → MoveTo, GetPosition
        │                                      ├─ LLM decide()
        │                                      │    → 输出 action JSON
        │                                      └─ cache_action_sequence()
        │                                      │
        ◄── SSE: {"actions": [...]} ───────────┘
        │
        ▼
handleMessage(bot, actions)
        │
        ▼
for each action:
    ExecuteAction(bot, action)
        │
        ├─ Move → OK → addToHistory("system", "完成")
        ├─ GetPosition → OK → addToHistory("system", "位置: (x, y, z)")
        ├─ BreakBlock → FAIL → addToHistory("system", "失败：没带镐")
        │                     → bot.chat("失败了，请回复 yes 重试")
        └─ 循环结束
```

### 3.2 错误恢复循环

```
玩家: "挖钻石"
  ↓
plan → [EquipItemInHand("iron_pickaxe"), MoveTo(...), BreakBlock(...)]
  ↓
EquipItemInHand → FAIL (背包里没有铁镐)
  ↓
系统写入历史: "任务失败：装备 iron_pickaxe 失败"
  ↓
bot.chat: "失败了，回复 yes 重试"
  ↓
玩家: "yes"
  ↓
下一轮 plan 看到历史中的失败信息
  → 这次输出 [CraftItem("iron_pickaxe"), EquipItemInHand, MoveTo, BreakBlock]
```

### 3.3 聊天历史结构

```json
[
  {"role": "player", "content": "帮我挖点钻石"},
  {"role": "bot",    "content": "好的，我先装备铁镐"},
  {"role": "system", "content": "任务执行到此失败，情况为：装备 iron_pickaxe 失败"},
  {"role": "player", "content": "yes"},
  {"role": "bot",    "content": "我先合成一把铁镐"},
  {"role": "system", "content": "整体任务已完成！"}
]
```

- `player` — 玩家消息
- `bot` — Bot 的 Chat 动作输出
- `system` — 任务执行状态 / 错误信息

---

## 4. 两层筛选机制

整个系统有三处使用了"关键词 + 嵌入"的两层筛选模式，设计思想和代码结构完全一致。

### 4.1 工具筛选 (`keyword_matcher.py` + `filter_tools`)

```
玩家消息: "帮我挖点钻石"
        │
  第 1 层: 中文关键词匹配
        │  "挖" → TOOL_KEYWORDS["BreakBlock"] → 命中
        │  "钻石" → TOOL_KEYWORDS["GetNearestTargetBlocks"]? → 命中
        │  关键词命中 → 这些工具必定保留
        │
  第 2 层: 嵌入语义过滤 (cosine_similarity, 阈值 0.3)
        │  tool_descriptions 与玩家消息算相似度
        │  保留超过阈值的工具
        │
  合并: 关键词命中 + 嵌入匹配 → 去重 → 始终保留 Chat
        │
  兜底: 如果前面都为空 → 返回全部工具
```

### 4.2 物品查询 (`item_query.py`)

```
玩家消息: "钻石能堆叠多少个"
        │
  触发检查: 消息含"多少"、"钻石" → 是
        │
  第 1 层: 精确/子串匹配
        │  1a. 中文名精确: cn_to_en("钻石") → "diamond" ✓
        │  1b. 英文精确: "diamond" in db
        │  1c. displayName 子串
        │  1d. 中文子串 fuzzy_cn_match
        │
  第 2 层: 嵌入匹配 (阈值 0.2，取 top-3)
        │  中文 query 对英文 displayName 做多语言嵌入
        │
  注入 prompt: "玩家提到的物品信息：\n  - diamond → 堆叠上限: 64"
```

### 4.3 技能匹配 (`skill_manager.py`)

```
玩家消息: "去挖钻石"
        │
  第 1 层: skill.name 包含匹配
        │  "挖钻石" in "去挖钻石" → 命中已保存的技能
        │
  第 2 层: skill.description 嵌入匹配 (阈值 0.2，最多追加 2 个)
        │
  注入 prompt:
        ## 可用技能参考
        技能: 挖钻石
        动作序列:
          1. EquipItemInHand(item=iron_pickaxe)
          2. GetNearestTargetBlocks(targetBlock=diamond_ore)
          ...
        你可以直接输出上述动作序列，无需重新规划。
```

### 4.4 为什么两层而不是一层？

| 层 | 成本 | 覆盖场景 | 漏掉代价 |
|---|---|---|---|
| 关键词（第 1 层） | 零（子串匹配） | 玩家直接说了工具/物品名 | 低，嵌入层兜底 |
| 嵌入（第 2 层） | 高（模型推理） | 玩家间接描述（"那个蓝色的矿物"） | 高，LLM 可能错误决策 |

两层互补，关键词拦截 70-80% 的常见情况，嵌入兜住剩余模糊请求。

---

## 5. LLM 提示词设计

### 5.1 当前使用的模型

```
API:      DeepSeek API (https://api.deepseek.com)
Model:    deepseek-v4-flash
Key:      环境变量 DeepSeek_API_KEY
```

### 5.2 Prompt 结构

```
# 角色

你是 AIPlayer，一个 Minecraft 机器人...

---

# 输出格式（严格 JSON）

{ "actions": [{"name": "...", "args": {}}] }

---

# 规则（按优先级排列）

  R1 — 身份：你是 "bot"，名字 AIPlayer
  R2 — 纯 JSON，无注释无解释
  R3 — 工具名必须来自下方列表，禁止编造
  R4 — 闲聊只输出 Chat
  R5 — 动作序列规则（核心）
    R5a — 必须用 Chat 开头 + 结尾
    R5b — 查询工具后必须紧跟固定 Chat 并结束
  R6 — 错误处理由系统负责，你别管
  R7 — 结尾 Chat 写预期成功后的内容

---

# 总结表

| 场景 | 序列模式 |
|---|---|
| 纯聊天 | [Chat] |
| 执行后汇报 | [Chat开头] → 工具... → Chat结尾] |
| 查询后询问 | [Chat开头] → 查询工具 → Chat(固定) ] |

---

# 可选工具列表        ← 动态注入，由 filter_tools 筛选后传入

# 当前已知信息        ← 动态注入（物品信息 / 技能参考）

# 聊天历史           ← 动态注入
```

### 5.3 关键设计决策

| 决策 | 原因 |
|---|---|
| **Chat 开头结尾** | 给玩家反馈，玩家能随时知道 bot 在干什么 |
| **查询后固定提问** | 避免 bot 查到信息后直接执行，不给玩家确认机会 |
| **错误处理剥离** | 让 LLM 专注于"正常时该怎么做"，不污染输出 |
| **规则优先级排列** | 减少规则冲突（R5a 必须 Chat 包裹 vs R5b 查询后结束） |
| **正面+反面示例** | LLM 对"不要做 X"的理解远不如"只做 Y"准确 |

---

## 6. 技能系统 (Skill)

### 6.1 原理

Skill 是将成功的任务执行序列保存下来，未来相似任务时直接复用的模板。

```
写入 ── 玩家完成任务后说: "保存 挖钻石"
          │
          plan() 检测到 "保存" 开头
          │
          短路: 不调 LLM，直接写文件
          │
          skills/挖钻石/skill.json
          {
            "name": "挖钻石",
            "description": "帮我挖点钻石",
            "actions": [
              {"name": "EquipItemInHand", "args": {"item": "iron_pickaxe"}},
              {"name": "GetNearestTargetBlocks", "args": {"targetBlock": "diamond_ore"}},
              ...
            ]
          }

读取 ── 下次玩家说 "去挖钻石"
          │
          plan() 前置扫描技能
          │
          匹配 → 注入 prompt 作为参考
          │
          LLM 看到 skill 后直接在 action 里复用
```

### 6.2 为什么保存可以短路 LLM？

"保存"不是决策行为——就是一次文件写操作。短路掉 LLM 调用：

```
Before:  玩家"保存挖钻石" → 调 LLM → LLM 输出 Chat("好的") → 返回
After:   玩家"保存挖钻石" → plan 检测 → 直接写文件 → 返回 Chat("已保存")
              省掉 1 次 LLM API 调用 + ~2 秒延迟
```

### 6.3 保存触发词

`"保存"`, `"存为"`, `"记录"`, `"存储"` 开头 + 技能名：

```
你: 保存 挖钻石流程    → 技能名: "挖钻石流程"
你: 保存               → 技能名: "skill_3" (自动编号)
```

---

## 7. 项目文件清单

### Node.js 端

| 文件 | 职责 |
|---|---|
| `MainLoop.js` | 入口，创建 Bot 实例 |
| `Bot.js` | Mineflayer 初始化 + 事件绑定（chat/spawn/error） |
| `MCP.js` | MCP 客户端：会话管理 / tool call / SSE 解析 / 动作执行循环 |
| `BotTools.js` | 19 个工具的定义 + 执行函数（Move, BreakBlock, CraftItem...） |
| `History.js` | 聊天历史环形缓冲区（上限 50 条） |
| `user_utils.js` | JSON 解析工具（SSE 提取 / 模糊 JSON 解析 / action 归一化） |
| `package.json` | 依赖：mineflayer, mineflayer-pathfinder, @modelcontextprotocol/sdk |

### Python 端

| 文件 | 职责 |
|---|---|
| `server_of_mcp.py` | **MCP Server 核心** — 唯一对外接口 `plan()` + 编排逻辑 |
| `LLMAgent.py` | LLM 调用 + 系统提示词 + JSON 响应解析 |
| `item_query.py` | 物品知识库加载 / 索引 / 两层匹配 / 上下文构建 |
| `skill_manager.py` | 技能加载 / 匹配 / 保存 / 动作序列缓存 |
| `keyword_matcher.py` | 中文触发词 → MCP 工具名映射 |
| `item_name_map.py` | ~250 个常用物品的中文→英文名映射字典 |
| `utils.py` | 仅保留 `load_item_json`（目前未直接使用） |

### 数据文件

| 路径 | 内容 |
|---|---|
| `ItemsData/item/items.json` | 1333 个物品（id, name, displayName, stackSize） |
| `ItemsData/food/foods.json` | 41 个食物（foodPoints, saturation） |
| `ItemsData/minecraft-data-data-pc/1.21.1/` | blocks.json, recipes.json, enchantments.json 等完整 MC 数据 |
| `EembeddingModelFiles/paraphrase-multilingual-MiniLM-L12-v2/` | 多语言嵌入模型（支持中英文语义匹配） |

---

## 8. 数据来源

### 已加载

| 数据 | 用途 |
|---|---|
| `items.json` (1333 条) | 物品名 + 堆叠上限，供 `item_query.py` 查询 |
| `item_name_map.py` (~250 条) | 中文→英文映射，第一层精确匹配 |

### 未加载但可用（位于 minecraft-data-data-pc/）

| 数据 | 如果加载可以回答 |
|---|---|
| `blocks.json` | "钻石矿用什么镐挖？硬度多少？" |
| `foods.json` | "牛排回复多少饥饿度？" |
| `recipes.json` | "铁镐怎么合成？需要什么材料？" |
| `enchantments.json` | "锋利 IV 需要多少级经验？" |

---

## 9. 部署与运行

### 9.1 环境要求

- Node.js 18+
- Python 3.10+
- 本地 Minecraft 服务器（localhost:25565）
- DeepSeek API Key（环境变量 `DeepSeek_API_KEY`）

### 9.2 启动步骤

```bash
# 1. 启动 Minecraft 服务器
java -jar minecraft_server.jar

# 2. 启动 Python MCP Server
cd Python
python server_of_mcp.py

# 3. 启动 Node.js Bot（另一个终端）
node MainLoop.js
```

### 9.3 环境变量

```bash
export DeepSeek_API_KEY="sk-xxxx"          # LLM API 密钥
export MCP_PLAN_URL="http://127.0.0.1:8001/mcp"  # MCP Server 地址（默认）
```

---

## 10. 架构图（简化版）

```
┌─────────┐   聊天    ┌──────────┐   JSON-RPC   ┌────────────┐   API   ┌──────────┐
│ 玩家     │────────▶│ Node.js  │─────────────▶│ Python     │───────▶│ DeepSeek │
│ (MC 聊天)│         │ MCP      │              │ FastMCP    │        │ LLM      │
│          │◀────────│ Client   │◀─────────────│ plan()     │◀───────│          │
└─────────┘   动作    └──────────┘   SSE 响应    └────────────┘        └──────────┘
                      │         ▲                 │
                      │ 执行     │ 错误回写          │
                      ▼         │                 │
                  ┌──────────┐  │    ┌─────────────────────┐
                  │ Mineflayer│  │    │ item_query.py        │
                  │ (MC Bot)  │  │    │ skill_manager.py     │
                  └──────────┘  │    │ keyword_matcher.py    │
                                │    │ item_name_map.py      │
                                │    └─────────────────────┘
                                │
                     ┌────────────────────┐
                     │ History.js (50条)   │
                     │ chatHistory 缓冲区  │
                     └────────────────────┘
```
