# AIPlayer — LLM 驱动的 Minecraft AI 玩家

一个基于 LLM（默认 DeepSeek，兼容任意 OpenAI 格式接口）的 Minecraft 自主决策机器人。玩家在游戏里对 Bot 说话，Bot 自主规划并执行动作。

## 架构总览

```
游戏内 @bot1 发消息
        │
        ▼
Control/（Node.js 游戏交互）── FastAPI HTTP :8000 ──► Decision/（Python AI 决策）──► LLM API
  Mineflayer + pathfinder         POST /plan/{bot_id}         OpenAI SDK + 结构化输出
```

- `Control/`：Node.js 层，负责与 Minecraft 交互（Mineflayer）、执行动作、维护聊天历史
- `Decision/`：Python 层，负责调用 LLM 做规划 / 反思 / 生成技能，通过 FastAPI 提供 HTTP 接口
- 两层通过 FastAPI HTTP 通信，端口 8000

## 目录结构

```
mc/
├── Control/                  # Node.js 游戏交互层
│   ├── launcher.js           # 多 Bot 启动器（node launcher.js 3）
│   ├── bot/index.js          # Bot 核心：监听聊天、规划-执行-续行主循环、敌怪监控
│   ├── bot/history.js        # 聊天历史（进程内内存，最多 50 条）
│   ├── core/registry.js      # 工具注册中心（自动扫描 / 热更新 / 同步 tools.json）
│   ├── tools/                # 22 个原子工具，一个工具一个文件
│   ├── actions/index.js      # 动作执行入口 / 任务状态收束 / 保存技能
│   ├── python/client.js      # FastAPI 客户端（状态采集 + 请求规划 + 执行动作）
│   ├── commands/quick.js     # 终端快捷指令（!背包 等）
│   ├── utils/                # 日志、规划响应解析
│   ├── config.json           # Minecraft 服务器地址、fastapi_url 等
│   └── package.json          # 依赖：mineflayer、mineflayer-pathfinder
├── Decision/                 # Python AI 决策层
│   ├── main.py               # FastAPI 入口（/plan /reflect /saveSkill /health）
│   ├── server.py             # 规划 / 反思 / 技能保存逻辑
│   ├── LLMAgent.py           # LLM 客户端（AsyncOpenAI，重试与错误分类）
│   ├── LLMData.py            # pydantic 结构化输出模型
│   ├── skill_manager.py      # 技能加载 / 查询 / 保存
│   ├── prompts/              # decide / reflect / generateSkill 提示词（YAML + Jinja2）
│   ├── skills/               # 已保存的技能（每技能一个目录）
│   ├── config.py             # 配置读取（根目录 .env）
│   └── requirements.txt      # Python 依赖
├── docker-compose.yml        # 一键 Docker 启动（control + decision）
├── Control/Dockerfile        # Node 镜像
├── Decision/Dockerfile       # Python 镜像
└── .env.example              # 环境变量示例（复制为 .env 后填写）
```

## 快速开始（本地运行）

前置：Node.js 18+（推荐 24）、Python 3.10+、一个 Minecraft 服务器（默认离线模式连接）。

### 1. 安装依赖

```bash
cd Control
npm install
cd ..

pip install -r Decision/requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env` 并填写：

```bash
OpenAI_API_KEY=你的APIKey
LLM_MODEL=deepseek-v4-flash        # 模型名，可按需修改
MODEL_BASE_URL=https://api.deepseek.com   # OpenAI 兼容接口地址
```

编辑 `Control/config.json`：

- `host`：Minecraft 服务器地址（本地服务器填 `127.0.0.1`，局域网填对应 IP；Docker 运行时保持默认 `host.docker.internal`）
- 若服务器端口不是 25565、或需要指定协议版本，可在 `Control/bot/index.js` 的 `mineflayer.createBot` 中取消注释 `port` / `version`

Bot 默认以离线模式登录，用户名固定为 `AIPlayer1`（多 Bot 时依次为 `AIPlayer2`…）。

### 3. 启动

终端 1 —— 启动 Python 决策服务（项目根目录）：

```powershell
$env:PYTHONPATH = "$PWD\Decision"
uvicorn Decision.main:app --port 8000
```

（cmd 对应：`set PYTHONPATH=%CD%\Decision`，再运行同一条 uvicorn 命令；开发时可加 `--reload`）

终端 2 —— 启动 Bot：

```bash
node Control/launcher.js 1
```

不带参数直接 `node Control/launcher.js` 会交互式询问启动几个 Bot；`node Control/launcher.js 3` 启动 3 个。

### 4. 使用

游戏内对 Bot 说话，消息以 `@bot1` 开头（多 Bot 时用 `@bot2`、`@bot3`…）：

```
@bot1 帮我挖点钻石
@bot1 我背包里有什么？
@bot1 跟着我
```

也可以在运行启动器的终端里输入快捷指令（不经过 LLM，直达动作执行）。不带 `@botN` 会分发到所有 Bot，带 `@botN` 只发给指定 Bot：

```
!背包      !物品      !状态      !坐标
!附近实体
!保存技能 转圈
!注册工具 {"name":"Xxx","args":["a"],"class":"DynamicTool","description":"...","code":"..."}
```

## Docker 运行

```bash
# 先配置根目录 .env（同上）
docker compose up --build
```

`docker-compose.yml` 会启动 `decision`（自动加载根目录 `.env`）和 `control` 两个容器，控制层通过 `http://decision:8000` 访问决策层。

## 核心特性

- **全量工具一次决策**：22 个原子工具全部加载，LLM 一次输出动作序列，无需分轮查询
- **N 步折中规划**：LLM 通过 `continue` 字段自主决定何时续行，兼顾实时性与多步任务
- **工具文件化**：一个工具 = `tools/` 目录下一个文件，注册中心自动扫描、目录监听热更新，变更自动同步 `tools.json` 供 Python 端热重载
- **环境状态自动注入**：每轮规划前自动执行 `GetState` / `GetAroundBlocks`，把最新状态注入 prompt
- **技能系统**：LLM 从历史中生成技能（子动作序列），通过 `skillProgress` 逐段续行推进
- **敌怪监控**：发现敌对生物自动中断任务并逃离，安全后恢复
- **多 Bot**：`launcher.js N` 一键启动多个独立 Bot 进程，注册 / 注销自动上报

## 技术栈

Node.js（mineflayer 4.x + mineflayer-pathfinder）、Python 3.10（FastAPI、OpenAI SDK、pydantic）、任意 OpenAI 兼容 LLM API（默认 DeepSeek）。

## 项目状态

核心功能已完成：Docker 化、工具热更新、环境状态注入、敌怪监控均已就绪。更详细的技术说明见 [DEVELOPER.md](DEVELOPER.md)。
