# AIPlayer — 你的 Minecraft AI 队友

一个能听懂中文的 Minecraft 机器人。你在游戏里打字说"帮我挖钻石"，它就自动规划并执行。

---

## 它能做什么

- 🎯 **听懂中文指令** — "过来"、"挖钻石"、"看看周围有什么"
- 🧭 **自主探索** — 移动、挖掘、放置方块、查询位置
- 🧠 **记住上次的事** — 退出后自动总结，下次加载
- ⚡ **快捷指令** — 终端输入 `!坐标`、`!血量`，实时反馈
- 📦 **物品知识库** — 知道每种物品的堆叠上限

---

## 你需要准备

| 项目 | 说明 |
|---|---|
| Minecraft 服务器 | Java版 1.21.1，本地运行 |
| Node.js | 18+ |
| Python | 3.10+ |
| DeepSeek API Key | 用于 AI 决策 |

---

## 快速开始

### 1. 下载项目

```bash
git clone https://github.com/你的用户名/aiplayer-mc-bot.git
cd aiplayer-mc-bot
```

### 2. 安装依赖

```bash
# Node.js 依赖
npm install

# Python 依赖
pip install fastmcp sentence-transformers scikit-learn tiktoken openai
```

### 3. 下载 AI 模型

项目需要嵌入模型来进行语义匹配，约 500MB：

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', cache_folder='./EembeddingModelFiles')"
```

### 4. 设置 API Key

```bash
set DeepSeek_API_KEY=sk-你的key
```

### 5. 配置存档目录

把你玩的世界存档放到项目同层目录下：

```
你的目录/
  ├── world1/              ← 你的存档（level.dat 所在文件夹）
  │     └── level.dat
  ├── world2/              ← 另一个存档
  └── aiplayer-mc-bot/     ← 项目文件夹（你刚下载的）
```

### 6. 启动

**终端 1** — 启动 Python MCP 服务：

```bash
cd Python
python server_of_mcp.py
```

**终端 2** — 启动 Bot：

```bash
node MainLoop.js
```

启动后终端会显示存档列表，输入编号选择当前要玩的存档即可。

---

## 在游戏里使用

### 自然语言指令（直接打字）

```
你: 帮我看看我在什么位置
Bot: 我在 (100, 64, 200)

你: 挖点钻石回来
Bot: 好的，我先装备铁镐...
```

### 快捷指令（终端输入，不进游戏）

| 输入 | 效果 |
|---|---|
| `!坐标` | 显示当前位置 |
| `!血量` | 显示血量和饱食度 |
| `!背包` | 显示背包物品 |
| `!物品` | 显示手持物品 |
| `!附近实体` | 显示周围生物 |

### 保存技能（游戏内聊天）

完成任务后说"保存 技能名"，Bot 会自动记住操作流程，下次可以直接复用。

---

## 常见问题

**Q: Bot 连不上服务器？**
确保 Minecraft 服务器已启动，地址为 localhost:25565，开启离线模式。

**Q: 提示 DeepSeek_API_KEY 未设置？**
参考步骤 4 设置环境变量。

**Q: 输入 !坐标 没反应？**
快捷指令是在启动 Bot 的终端窗口输入的，不是在游戏聊天框。

**Q: 启动时没有看到我的存档？**
确保你的存档文件夹在项目目录的上级目录中（和项目文件夹同级）。

---

## 项目状态

⚠️ **Demo / Work in Progress** — 核心功能可用，图形界面尚未完成。
