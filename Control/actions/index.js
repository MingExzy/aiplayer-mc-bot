/**
 * 动作执行入口
 * （由 BotTools.js 演变而来，现已改为纯注册中心分发）
 *
 * 职责：
 *   - ExecuteAction：按工具名交给 core/registry.js 执行（所有工具都是 tools/ 下的独立文件）
 *   - TaskCompleteCheck：每个动作执行后的统一状态收束
 *   - SaveSkill：调用 Python 层生成并保存技能
 *
 * 工具本身不再写死在本文件：一个工具 = tools/ 目录下一个文件，
 * 格式 { name, args, class, description, execute(bot, args) }，由注册中心统一加载。
 */
const { addToHistory, getHistory } = require('../bot/history')
const config = require('../config.json')
const registry = require('../core/registry')


async function SaveSkill(Bot, skill_name) {
    if (typeof fetch !== 'function') {
        throw new Error('当前运行环境不支持 fetch')
    }

    const API_BASE = process.env.FASTAPI_URL || config.fastapi_url
    const BOT_ID = process.env.BOT_ID || '1'
    const response = await fetch(`${API_BASE}/saveSkill/${BOT_ID}?skill_name=` + encodeURIComponent(skill_name), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: 'console', chatHistory: getHistory(), skillprogress: '', status: {} }),
    })

    if (!response.ok) {
        throw new Error(`FastAPI 返回 ${response.status}: ${await response.text()}`)
    }

    const data = await response.json()
    const resultText = data.result || JSON.stringify(data)
    Bot.chat(resultText)
    addToHistory("system", resultText)
}

function normalizeToolName(name) {
    return String(name || '').trim()
}

function normalizeArgs(args) {
    if (!args) {
        return {}
    }

    if (typeof args === 'string') {
        try {
            return JSON.parse(args)
        } catch (_) {
            return { value: args }
        }
    }
    return args
}

async function TaskCompleteCheck(bot, success, detail, nextStep) {
    // 任务完成或失败时，统一走这个出口；这里不再负责提问，只做状态收束。
    const statusText = success ? '任务完成' : '任务失败'
    const message = nextStep
        ? `${statusText}: ${detail}。下一步：${nextStep}` : `${statusText}: ${detail}`

    if (statusText === '任务失败') {
        await bot.chat("任务失败了，情况是：" + detail + "再次输入请求以进行重新尝试。")
        return addToHistory("system", `任务执行到此失败，情况为：${detail}`)
    }

    if (nextStep == "当前动作序列执行完毕") {
        return addToHistory("system", `当前动作序列执行完毕: ${detail}`)
    }

    return addToHistory("system", message)
}


async function ExecuteAction(Bot, Actions) {
    const normalizedActions = normalizeToolName(Actions.name)
    const args = normalizeArgs(Actions.args)
    // 所有工具统一走注册中心（大小写不敏感）；未知工具由 registry 抛错
    return await registry.execute(Bot, normalizedActions, args)
}


module.exports = {
    ExecuteAction,
    TaskCompleteCheck,
    SaveSkill,
}
