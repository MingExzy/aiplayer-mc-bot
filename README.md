# AIPlayer — LLM 驱动的 Minecraft AI 玩家

一个基于 DeepSeek LLM 的 Minecraft 自主决策机器人。玩家在游戏中打字，Bot 自主规划并执行动作。

## 快速开始

```bash
# 安装依赖
npm install
pip install fastmcp openai

# 设置 API Key
set DeepSeek_API_KEY=sk-xxx

# 启动 MCP 服务（终端 1）
cd Python && python server_of_mcp.py

# 启动 Bot（终端 2）
node MainLoop.js
```

启动后在游戏中对 Bot 说话即可。

## 架构

```
Node.js (游戏交互) ← MCP/SSE → Python (AI 决策) ← API → DeepSeek LLM
     │                             │
     ▼                             ▼
  Mineflayer 驱动               plan() 决策循环
  ExecuteAction 执行            N步折中规划
```

## 核心设计

- **N步折中规划**：LLM 自主决定何时输出完整动作、何时续行，兼顾实时性和多步依赖
- **统一决策入口**：22 个工具全部加载，LLM 一次输出，无需分轮查询
- **技能系统**：保存常用操作流，skillProgress 续行推进
- **SSE 优化**：只读第一条事件即断开，消除 30 秒超时等待

## 技术栈

Node.js, Python, MCP Protocol, DeepSeek API, Mineflayer, FastMCP

## 项目状态

核心功能已完成，正在开发：环境状态监测器。
