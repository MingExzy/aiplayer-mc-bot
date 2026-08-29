/**
 * 机器人核心
 * （原 Bot.js）
 *
 * 职责：
 *   - initBot：创建 Mineflayer Bot 并挂载路径寻路插件
 *   - 聊天监听：处理 @botX 消息，执行「规划 → 执行 → 续行」主循环
 *   - 敌对生物监控：发现危险时中断任务并逃离，安全后恢复
 */
const mineflayer = require('mineflayer')
const config = require('./config.json')
const { pathfinder, Movements, goals: { GoalBlock } } = require('mineflayer-pathfinder')
const Vec3 = require('vec3')
const { addToHistory, getHistory } = require('./history')
const { requestPlan, executeActions, collectStatus } = require('../python/client')
const { normalizeActionList } = require('../utils/plan-parse')
const { processCommand } = require('../commands/quick')
const logger = require('../utils/logger')
const crypto = require('crypto')

let BOT_ID = '1'
let _busy = false
let _interrupted = false
let _pendingPlayerMsg = ""  // 被中断时保存玩家需求
let _safeCount = 0          // 连续安全扫描计数
let _monitorTimer = null

function setBotId(id) { BOT_ID = id }

const HOSTILE_MOBS = new Set([
  "zombie","skeleton","creeper","spider","enderman","witch",
  "slime","blaze","ghast","magma_cube","silverfish","vex","evoker"
])



function findHostileNearby(bot, range) {
  let nearest = null
  let minDist = range
  for (const id in bot.entities) {
    const e = bot.entities[id]
    if (!e || !e.position || e.type === 'player' || e.type === 'other') continue
    const dist = e.position.distanceTo(bot.entity.position)
    if (dist <= range) console.log(`[monitor] 附近实体: ${e.name||'?'} type=${e.type} id=${e.entityType} 距离=${dist.toFixed(1)}`)
    if (e.type !== 'mob' && e.type !== 'hostile') continue
    const eName = (e.name || e.displayName || '').toLowerCase()
    if (![...HOSTILE_MOBS].some(m => eName.includes(m))) continue
    if (dist > range) continue
    if (!nearest || dist < minDist) { nearest = e; minDist = dist }
  }
  if (nearest) console.log(`[monitor] 敌对: ${nearest.name||nearest.displayName}`)

  return nearest
}

async function startMonitor(bot) {
  if (_monitorTimer) return
  _monitorTimer = setInterval(async () => {
    if (!bot || !bot.entity) return
    const hostile = findHostileNearby(bot, 16)
    if (hostile) {
      if (_busy) _interrupted = true
      _safeCount = 0
      // 逃离
      const dx = bot.entity.position.x - hostile.position.x
      const dz = bot.entity.position.z - hostile.position.z
      const angle = Math.atan2(dz, dx)
      const fx = bot.entity.position.x + Math.cos(angle) * 30
      const fz = bot.entity.position.z + Math.sin(angle) * 30
      try {
        await bot.pathfinder.goto(new (require('mineflayer-pathfinder').goals.GoalBlock)(Math.floor(fx), bot.entity.position.y, Math.floor(fz)))
      } catch {}
    } else if (_interrupted) {
      _safeCount++
      if (_safeCount >= 3) {
        _interrupted = false
        addToHistory("system", `敌对生物已远离，中断的任务 "${_pendingPlayerMsg}" 可重新发送`)
        bot.chat(`已安全，重新发送需求: ${_pendingPlayerMsg}`)
      }
    }
  }, 2000)
}

function stopMonitor() {
  if (_monitorTimer) { clearInterval(_monitorTimer); _monitorTimer = null }
}

let bot = null



function initBot(botname) {
    // 初始化 Mineflayer 机器人，并挂载路径寻路插件。
    bot = mineflayer.createBot({
        host: config.host, // minecraft 服务器的 IP 地址
        username: botname, // minecraft 用户名
        // password: '12345678' 
        // port: 25565,
        // version: '1.21.1'
        // auth: 'mojang'
    })

    bot.loadPlugin(pathfinder)

    bot.on('spawn', async () => {
        const defaultMove = new Movements(bot)
        bot.pathfinder.setMovements(defaultMove)
        console.log('Bot 已生成，路径寻路插件已加载。')
        startMonitor(bot)
    })

    bot.on('chat', async (username, message) => {
        if (username === bot.username) return
        // 只处理 @botX 消息，其他 Bot 的反馈和闲聊全部忽略
        const botTag = `@bot${BOT_ID}`
        if (!message.startsWith(botTag)) return
        message = message.slice(botTag.length).trim()

        // 执行中拒绝新请求
        if (_busy) {
            bot.chat(`正在执行任务中，请稍后再发`)
            return
        }
        _interrupted = false

        addToHistory('player', `${username}: ${message}`)
        bot.chat(`思考中...`)
        _busy = true; _interrupted = false; _safeCount = 0
        const trace_id = crypto.randomUUID()
        logger.info('task_start', { trace_id, username, message })
        _pendingPlayerMsg = message
        let keepPlanning = true
        let activeSkillProgress = null
        let currentStatus = {}
        while (keepPlanning) {
            if (_interrupted) {
                addToHistory("system", `任务被敌对生物中断: ${_pendingPlayerMsg}`)
                break
            }
            try {
                // 自动采集环境感知工具的状态（GetState / GetAroundBlocks），随请求注入 prompt
                currentStatus = await collectStatus(bot)
                // 请求 Python 层规划（FastAPI /plan/:botId）
                const rawPlan = await requestPlan(username, message, activeSkillProgress, currentStatus, trace_id)
                const actions = normalizeActionList(rawPlan)
                const shouldContinue = rawPlan?.continue === true
                activeSkillProgress = rawPlan?.skillProgress || null

                // 执行动作
                const result = await executeActions(bot, actions)
                if (shouldContinue && result?.success) {
                    addToHistory("system", `当前动作序列执行完毕，继续任务，再次明确用户${username}需求：${message}`)
                }
                else if (result?.success) {
                    addToHistory("system", `整体任务已完成`)
                    logger.info('task_complete', { trace_id, username, message })
                    break
                }
                else {
                    // 任务失败 → 触发反思
                    try {
                        const resp = await fetch(`${process.env.FASTAPI_URL || config.fastapi_url}/reflect/${BOT_ID}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json',
                                        'X-Trace-ID': trace_id || "",
                            },
                            body: JSON.stringify({ user: username, chatHistory: getHistory(), status: currentStatus }),
                            signal: AbortSignal.timeout(10000)
                        })
                        const analysis = await resp.json()
                        addToHistory("system", `失败反思: ${analysis.result || analysis}`)
                    } catch (err) {
                        logger.error('reflect_failed', { trace_id, error: err && err.message })
                    }
                    break
                }

            } catch (err) {
                logger.error('task_failed', { trace_id, error: err.message })
                // 异常信息已在执行层记录，直接退出
                break
            }
        }
        _busy = false
    })
    bot.on('error', err => logger.error('bot_error', { error: err && err.message }))
    bot.on('end', (reason) => {
        console.log('Bot 断开:', reason, '- 已退出。')
    })
    bot.on('kicked', console.log)

    return bot
}

module.exports = {
    initBot,
    setBotId,
}
