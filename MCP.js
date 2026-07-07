

const fs = require("fs");
const path = require("path");
const config = require("./config.json");
const { getHistory } = require("./History");
const { ExecuteAction, TaskCompleteCheck } = require("./BotTools");
const { extractJsonFromSSE,parseJsonCandidate, normalizeActionList } = require("./user_utils");

function getSessionId() { return config.mcp_session_id }
function setSessionId(id) { config.mcp_session_id = id; saveConfig() }
function getMCPUrl() { return config.mcp_url }
function saveConfig() {
  fs.writeFileSync(path.join(__dirname, "config.json"), JSON.stringify(config, null, 4), "utf-8");
}

// 从 fetch Response 中读取完整 SSE 事件（data:xxx\n\n），不等连接关闭
async function readSSEFromResponse(response) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    if (buffer.includes("\n\n")) break
  }
  reader.cancel()
  return buffer
}

async function initMCPSession() {
  const response = await fetch('http://127.0.0.1:8001/mcp', { method: 'GET' });
  const sessionId = response.headers.get('Mcp-Session-Id');
  if (!sessionId) throw new Error('无法获取 MCP session ID');
  setSessionId(sessionId)
  console.log('MCP session established:', sessionId);
  //发送初始化请求：
  const initResp = await fetch('http://127.0.0.1:8001/mcp', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': sessionId
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: {
          name: 'minecraft-bot',
          version: '1.0.0'
        }
      },
      id: 2
    })
  });

  const initText = await initResp.text();
  console.log('Initialize response:', initText);
  console.log('MCP session established:', getSessionId());
}

async function requestTaskPlan(username, message, skillProgress) {
  if (typeof fetch !== 'function') {
    throw new Error('当前运行环境不支持 fetch')
  }

  // 发给 MCP 的 payload 也是标准 JSON，history 会保留前面统一好的消息结构。
  const response = await fetch(getMCPUrl(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': getSessionId()
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'plan',
        arguments: {
          chatHistory: getHistory(),
          skill_progress: skillProgress ? JSON.stringify(skillProgress) : ''
        }
      },
      id:1,
    }),
    signal: AbortSignal.timeout(60000)
  })

  console.log('发送给 plan 的参数:', JSON.stringify({ chatHistory: getHistory()}, null, 2));
  // 从 SSE 流中只读第一条 data: 行，不等连接关闭
  const text = await readSSEFromResponse(response)
  if (!response.ok) {
    throw new Error(`MCP 服务器返回 ${response.status}: ${text}`)
  }

  const data = extractJsonFromSSE(text)
  console.log('SSE 解析结果:', JSON.stringify(data, null, 2));
  const resulttext = data.result.content[0]?.text || ''
  return parseJsonCandidate(resulttext)
}


const _ACTION_FEEDBACK = {
    move: "正在移动...",
    jump: "跳跃中...",
    turn: "正在转向...",
    sneak: "潜行中...",
    lookat: "正在观察...",
    moveto: "正在前往目标...",
    equipiteminhand: "正在装备物品...",
    useiteminhand: "正在使用物品...",
    throwitems: "丢弃物品中...",
    placeblock: "放置方块中...",
    breakblock: "挖掘中...",
    getposition: "查询位置中...",
    getstate: "查询状态中...",
    getinventory: "检查背包...",
    getiteminhand: "检查手持物品...",
    getaroundentities: "扫描周围...",
    getaroundnearesttargetblocks: "搜索方块中...",
    getrecipesforitem: "查询配方...",
    followplayer: "跟随中...",
    craftitem: "制作中...",
    chat: "",
}

async function handleMessage(bot, actions) {
  try {


    if (!actions.length) {
      await TaskCompleteCheck(bot, false, 'MCP 返回了空任务。', '请回复 yes 重新请求，或继续输入其他内容。')
      return { success: false, reason: 'empty_actions' }
    }

    for (let index = 0; index < actions.length; index += 1) {
      const action = actions[index]
      const nextAction = actions[index + 1]

      try {
        const feedback = _ACTION_FEEDBACK[(action.name || '').toLowerCase()]
        if (feedback) {
          bot.chat(feedback)
          await new Promise(r => setTimeout(r, 500))
        }
        const executionResult = await ExecuteAction(bot, action)

        if (executionResult?.stop) {
          return { success: false, reason: 'stopped' }
        }
    
        await TaskCompleteCheck(
          bot,
          true,
          executionResult?.message || `动作 ${action.name} 已完成。`,
          nextAction
            ? `继续执行下一步动作 ${nextAction.name}`
            : '当前动作序列执行完毕'
        )
      } catch (err) {
        await TaskCompleteCheck(
          bot,
          false,
          `动作 ${action.name} 执行失败：${err.message}`,
          '请重试或继续输入其他内容。'
        )
        return { success: false, reason: 'action_error', detail: err.message }
      }
    }
    return { success: true }
  } catch (err) {
    console.error('处理玩家消息失败:', err)
    await TaskCompleteCheck(bot, false, `任务中断：${err.message}`, '请重试或继续输入其他内容。')
    return { success: false, reason: 'exception', detail: err.message }
  }
}

async function requestSummary(chatHistory) {
  const response = await fetch(getMCPUrl(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': getSessionId()
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'summarize',
        arguments: { chatHistory }
      },
      id: 2
    }),
    signal: AbortSignal.timeout(15000)
  })

  const text = await readSSEFromResponse(response)
  if (!response.ok) {
    throw new Error(`MCP 返回 ${response.status}: ${text}`)
  }

  const data = extractJsonFromSSE(text)
  return data.result.content[0]?.text || ''
}


module.exports = {
  initMCPSession,
  handleMessage,
  requestTaskPlan,
  requestSummary,
}