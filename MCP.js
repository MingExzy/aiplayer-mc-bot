

const { getHistory } = require("./History");
const { ExecuteAction, TaskCompleteCheck } = require("./BotTools");
const { extractJsonFromSSE,parseJsonCandidate, normalizeActionList } = require("./user_utils");


const MCP_PLAN_URL = process.env.MCP_PLAN_URL || 'http://127.0.0.1:8001/mcp'
let mcpSessionId = null

async function initMCPSession() {
  const response = await fetch('http://127.0.0.1:8001/mcp', { method: 'GET' });
  mcpSessionId = response.headers.get('Mcp-Session-Id');
  if (!mcpSessionId) throw new Error('无法获取 MCP session ID');
  console.log('MCP session established:', mcpSessionId);
  //发送初始化请求：
  const initResp = await fetch('http://127.0.0.1:8001/mcp', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': mcpSessionId
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
  console.log('MCP session established:', mcpSessionId);
}

async function requestTaskPlan(username, message,tools) {
  if (typeof fetch !== 'function') {
    throw new Error('当前运行环境不支持 fetch')
  }

  // 发给 MCP 的 payload 也是标准 JSON，history 会保留前面统一好的消息结构。
  const response = await fetch(MCP_PLAN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': mcpSessionId
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'plan',
        arguments: {
          chatHistory: getHistory(),
          tools:tools,
        }
      },
      id:1,
    }),
    signal: AbortSignal.timeout(30000)
  })

  console.log('发送给 plan 的参数:', JSON.stringify({ chatHistory: getHistory(), tools }, null, 2));
  const text = await response.text()
  if (!response.ok) {
    throw new Error(`MCP 服务器返回 ${response.status}: ${text}`)
  }

  const data = extractJsonFromSSE(text)
  console.log('SSE 解析结果:', JSON.stringify(data, null, 2));
  const resulttext = data.result.content[0]?.text || ''
  return parseJsonCandidate(resulttext)
}


async function handleMessage(bot, actions, isQueryTask = false) {
  try {


    if (!actions.length) {
      await TaskCompleteCheck(bot, false, 'MCP 返回了空任务。', '请回复 yes 重新请求，或继续输入其他内容。')
      return { success: false, reason: 'empty_actions' }
    }

    for (let index = 0; index < actions.length; index += 1) {
      const action = actions[index]
      const nextAction = actions[index + 1]

      try {
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
            : isQueryTask
              ? '查询任务完成'
              : '没有下一步动作，整体任务已完成。'
        )
      } catch (err) {
        await TaskCompleteCheck(
          bot,
          false,
          `动作 ${action.name} 执行失败：${err.message}`,
          '请回复 yes 重试，或继续输入其他内容。'
        )
        return { success: false, reason: 'action_error', detail: err.message }
      }
    }
    return { success: true }
  } catch (err) {
    console.error('处理玩家消息失败:', err)
    await TaskCompleteCheck(bot, false, `任务中断：${err.message}`, '请回复 yes 重试，或继续输入其他内容。')
    return { success: false, reason: 'exception', detail: err.message }
  }
}

async function requestSummary(chatHistory) {
  const response = await fetch(MCP_PLAN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': mcpSessionId
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

  const text = await response.text()
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