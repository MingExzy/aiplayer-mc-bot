# AIPlayer — Minecraft AI 玩家（开发者文档）

---

## 目录

1. [整体架构](#1-整体架构)
2. [核心流程](#2-核心流程)
3. [工具设计](#3-工具设计)
4. [技能系统](#4-技能系统)
5. [MCP 通信](#5-mcp-通信)
6. [Prompt 设计](#6-prompt-设计)
7. [测试](#7-测试)
8. [演化记录](#8-演化记录)

---

## 1. 整体架构

```
Node.js (游戏交互)              Python (AI 决策)             API
─────────────────              ─────────────────           ────────
Bot.js (Mineflayer 客户端)      server_of_mcp.py            DeepSeek LLM
  ├─ on('chat') 监听聊天        ├─ plan() 决策入口
  ├─ handleMessage 执行循环     │   ├─ decide() 统一决策
  └─ ExecuteAction 工具执行     │   ├─ skillProgress 续行
                                │   └─ 异常兜底 Chat
                                ├─ summarize (记忆)
                                └─ saveSkill (技能保存)
      │                                │
      └────────── MCP/SSE ────────────┘
```

Node.js 和 Python 通过 MCP 协议跨进程通信，Python 调用 DeepSeek LLM 做决策。

### 核心技术选择

- LLM 只做决策，不做底层控制
- 22 个工具全部加载，LLM 一次出动作，不需要分轮查询
- N步折中：LLM 通过 `continue` 字段自选断点

---

## 2. 核心流程

### 正常执行

```
玩家: "帮我挖点钻石"

plan() → decide(chatHistory, all_tools, skill_context)
  ↓
LLM 输出: {"actions": [Chat, EquipItemInHand, GetAroundNearestTargetBlocks],
           "continue": true, "skillProgress": null}
  ↓
handleMessage 逐条执行 → 失败时记录到历史
  ↓
continue=true → addToHistory("继续任务，明确用户需求")
  → 再次调 plan() → decide() 看到续行消息
  ↓
LLM 输出: {"actions": [Chat, MoveTo, BreakBlock, Chat],
           "continue": false}
  ↓
整体任务已完成
```

### 技能续行

```
玩家: "转圈"

plan() → decide() → LLM 选择执行技能
  ↓
LLM 输出: {"actions": [Chat, Move, Turn...],
           "continue": true,
           "skillProgress": {"name":"转圈","next":1}}
  ↓
Node.js 下次调 plan() 时带上 skillProgress
  ↓
plan() 进入技能续行分支 → 只展示剩余序列的工具
  → decide() → LLM 严格按技能输出
```

---

## 3. 工具设计

当前 22 个工具，全量加载到 prompt，LLM 一次看到全部描述：

| 类别 | 工具 | 说明 |
|---|---|---|
| 交互 | Chat | 发消息 |
| 移动 | Move, MoveTo, Jump, Sneak, run, Turn, LookAt | 移动和控制 |
| 物品 | EquipItemInHand, UseItemInHand, ThrowItems | 物品操作 |
| 方块 | PlaceBlock, BreakBlock | 建造/破坏 |
| 查询 | GetPosition, GetState, GetInventory, GetItemInHand, GetAroundEntities, GetAroundNearestTargetBlocks, GetRecipesForItem | Bot 状态查询 |
| 高级 | CraftItem, FollowPlayer | 合成/跟随 |

### 工具粒度原则

- **过低**（LLM 不该做）：Jump、run → 规则就能实现
- **合适**（LLM 该决策）：装备工具前先查背包 → EquipItemInHand → BreakBlock
- **过高**（规则更好）：建筑蓝图放置 → LLM 决策结构，规则执行放置

---

## 4. 技能系统

### 保存

```
generate_skill(chatHistory, name)
  → LLM 从历史中提取工具名序列
  → 按查询工具拆分、满 10 步截断
  → 存入 skills/{name}/skill.json
```

### 匹配与执行

正常执行时，技能名称和描述随 prompt 展示。LLM 自主判断是否执行。
续行时通过 `skillProgress` 推进，只展示当前子序列的工具。

---

## 5. MCP 通信

### 传输方式

FastMCP + streamable-http (HTTP/SSE)

### 会话流程

```
GET  /mcp       → 获取 Mcp-Session-Id
POST /mcp       → initialize 握手
POST /mcp       → tools/call (调 plan/summarize/saveSkill)
```

### SSE 关键处理

Node.js 用 `response.body.getReader()` 读取 SSE 流，读到 `\n\n`（事件结束符）后立即断开连接。避免因 SSE 流不关闭导致的 `response.text()` 超时等待。

```
改造前: response.text() → 等待连接关闭 → 30s 超时
改造后: readSSEFromResponse() → 读到 \n\n 就断 → 5ms
```

---

## 6. Prompt 设计

### 输出格式

```json
{
  "actions": [{"name": "ToolName", "args": {}}],
  "continue": true/false,
  "skillProgress": null / {"name": "技能名", "next": 索引}
}
```

### 规则

- R1: 身份（bot 名为 AIPlayer）
- R2: 纯 JSON，无注释
- R3: 工具名必须来自列表
- R4: 技能执行（高度匹配才用，闲聊不执行）
- R5: 动作截断（查询工具末位续行；满 10 步截断）
- R6: Chat 包裹（非续行首尾 Chat，续行首 Chat 尾仅末序列）
- R7: 错误处理（系统兜底）
- R8: 数据时效性

---



---

## 7. 演化记录

| 阶段 | 状态 | 说明 |
|---|---|---|
| 原子工具 + 全量加载 | ✅ 当前 | 22 工具一次加载，LLM 直接输出 |
| N步折中（continue） | ✅ 当前 | LLM 自选断点 |
| 技能系统 + skillProgress | ✅ 当前 | 保存+续行 |
| SSE 流式优化 | ✅ 当前 | readSSEFromResponse |
| 异步 LLM 调用 | ✅ 当前 | AsyncOpenAI |
| 关键词预选 + tool_queries | ❌ 移除 | 全量加载后不需要 |
| 嵌入模型匹配 | ❌ 移除 | 去掉 500MB 模型依赖 |
| 思考+执行分离 | ❌ 尝试后回退 | 增加复杂度但没有实质收益 |
| Agentic 经验回放 | ⏸ 暂缓 | 需要区分 LLM 错误和环境限制 |
