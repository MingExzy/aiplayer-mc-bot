/**
 * 快捷指令（终端 / 控制台直连执行，不经过 LLM）
 * （原 rules.js）
 *
 * 职责：把 !背包 / !坐标 / !保存技能 / !注册工具 等快捷指令映射到具体功能。
 */
const path = require('path')
const { ExecuteAction, TaskCompleteCheck, SaveSkill } = require('../actions')
const { addToHistory } = require('../bot/history')
const registry = require('../core/registry')

const command_matches = {
    "!背包":     { tool: "GetInventory",        needsArg: false },
    "!物品":     { tool: "GetItemInHand",       needsArg: false },
    "!状态":     { tool: "GetState",            needsArg: false },
    "!坐标":     { tool: "GetState",            needsArg: false },
    "!附近实体":  { tool: "GetAroundEntities",   needsArg: false },
    "!保存技能":  { tool: "SaveSkill",          needsArg: true, directFunc: SaveSkill },
    "!注册工具":  { tool: "RegisterTool",       needsArg: true, directFunc: registerTool },
}

/**
 * 运行时注册工具：输入 JSON 定义 → 生成 tools/<name>.js → 注册进注册表 → 同步 tools.json。
 * 定义格式：{"name":"Xxx","args":["a"],"class":"DynamicTool","description":"...","code":"...函数体..."}
 * code 是 async execute(bot, args) 的函数体源码，可用 bot、args 两个变量。
 */
async function registerTool(bot, arg) {
    let def
    try {
        def = JSON.parse(arg)
    } catch (_) {
        bot.chat('参数必须是 JSON：{"name":"Xxx","args":[],"class":"DynamicTool","description":"...","code":"..."}')
        return
    }
    try {
        const filePath = registry.createToolFile(def, path.join(__dirname, '..', 'tools'))
        registry.registerFromFile(filePath)
        registry.syncToolsJson()
        bot.chat(`工具 ${def.name} 已注册，Python 端将在下一次规划时自动加载`)
        addToHistory("system", `运行时注册工具: ${def.name}`)
    } catch (err) {
        bot.chat(`注册失败: ${err.message}`)
    }
}


function matchCommand(input) {
    const trimmed = input.trim()
    // 按第一个空格拆成命令和参数
    const spaceIdx = trimmed.indexOf(' ')
    const cmd = spaceIdx > 0 ? trimmed.slice(0, spaceIdx) : trimmed
    const arg = spaceIdx > 0 ? trimmed.slice(spaceIdx + 1).trim() : ''

    const rule = command_matches[cmd]
    if (!rule) return { error: null, cmd, arg: null }

    if (rule.needsArg && !arg) {
        return { error: `指令 ${cmd} 需要参数，用法: ${cmd} <参数>`, cmd, arg: null }
    }

    return { error: null, cmd, rule, arg }
}


async function processCommand(bot, input) {
    const parsed = matchCommand(input)

    if (!parsed.rule) {
        const available = Object.keys(command_matches).join(', ')
        bot.chat(`未知指令: ${input}, 可用指令包括: ${available}`)
        return
    }

    if (parsed.error) {
        bot.chat(parsed.error)
        return
    }

    const { rule, arg } = parsed
    addToHistory("system", `执行快捷指令： ${input}`)

    // 直接函数调用（不走 ExecuteAction）
    if (rule.directFunc) {
        try {
            await rule.directFunc(bot, arg)
        } catch (err) {
            bot.chat(`指令 ${input} 执行失败: ${err.message}`)
        }
        return
    }

    // 普通工具执行
    const action = { name: rule.tool, args: {} }
    try {
        const result = await ExecuteAction(bot, action)
        bot.chat(result.message)
        await TaskCompleteCheck(bot, true, result.message, '当前动作序列执行完毕')
    } catch (err) {
        bot.chat(`快捷指令 ${input} 执行失败: ${err.message}`)
        await TaskCompleteCheck(bot, false, err.message, '请重试或继续输入其他内容。')
    }
}

module.exports = {
    processCommand,
}
