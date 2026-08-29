/**
 * Python 推理层 FastAPI 客户端
 * （原 MCP.js，早期走 MCP/SSE，现已改为 FastAPI HTTP）
 *
 * 职责：
 *   - collectStatus：自动执行「环境感知工具」（GetState / GetAroundBlocks），采集 Bot 状态快照
 *   - requestPlan：POST /plan/:botId 请求规划，随请求携带状态快照（status 字段）
 *   - executeActions：按序执行规划返回的动作序列（原名 handleMessage）
 */
const { getHistory } = require('../bot/history')
const { ExecuteAction, TaskCompleteCheck } = require('../actions')
const registry = require('../core/registry')
const { fastapi_url, auto_status_tools = [] } = require('../config.json')
const logger = require('../utils/logger')
const BOT_ID = process.env.BOT_ID || '1'
const API_BASE = process.env.FASTAPI_URL || fastapi_url


/**
 * 自动采集 Bot 状态快照：逐个执行 config.json 里 auto_status_tools 指定的工具，
 * 把每个工具返回的 message 收集成 {工具名: 状态文本}，随规划请求一起发给 Python。
 * 单个工具失败不影响整体（失败信息也会传给 LLM 参考）。
 */
async function collectStatus(bot) {
  const status = {}
  for (const toolName of auto_status_tools) {
    try {
      const result = await registry.execute(bot, toolName, {})
      status[toolName] = (result && result.message) || '（无返回）'
    } catch (err) {
      status[toolName] = `获取失败: ${err.message}`
    }
  }
  return status
}

async function requestPlan(username, message, skillProgress, status, trace_id) {
  if (typeof fetch !== 'function') {
    throw new Error('当前运行环境不支持 fetch')
  }

  const start = Date.now()
  try {
    const response = await fetch(`${API_BASE}/plan/${BOT_ID}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json',
                  'X-Trace-ID': trace_id || "",
      },
      body: JSON.stringify({
        user: username,
        chatHistory: getHistory(),
        skillprogress: skillProgress ? JSON.stringify(skillProgress) : '',
        status: status || {}
      }),
      signal: AbortSignal.timeout(60000)
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(`FastAPI 返回 ${response.status}: ${text}`)
    }

    const data = await response.json()
    logger.info('plan_success', {
      trace_id: trace_id || '',
      bot_id: BOT_ID,
      duration_ms: Date.now() - start,
      actions: Array.isArray(data?.actions) ? data.actions.length : 0
    })
    return data
  } catch (err) {
    logger.error('plan_failed', {
      trace_id: trace_id || '',
      bot_id: BOT_ID,
      duration_ms: Date.now() - start,
      error: err.message
    })
    throw err
  }
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

async function executeActions(bot, actions) {
  try {
    if (!actions.length) {
      await TaskCompleteCheck(bot, false, '规划返回了空任务。', '请重试。')
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
          bot, true,
          executionResult?.message || `动作 ${action.name} 已完成。`,
          nextAction
            ? `继续执行下一步动作 ${nextAction.name}`
            : '当前动作序列执行完毕'
        )
      } catch (err) {
        await TaskCompleteCheck(
          bot, false,
          `动作 ${action.name} 执行失败：${err.message}`,
          '请重试。'
        )
        return { success: false, reason: 'action_error', detail: err.message }
      }
    }
    return { success: true }
  } catch (err) {
    console.error('处理玩家消息失败:', err)
    await TaskCompleteCheck(bot, false, `任务中断：${err.message}`, '请重试。')
    return { success: false, reason: 'exception', detail: err.message }
  }
}

module.exports = {
  collectStatus,
  requestPlan,
  executeActions,
}
