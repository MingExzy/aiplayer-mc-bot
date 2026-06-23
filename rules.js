const { ExecuteAction, TaskCompleteCheck } = require('./BotTools')
const { addToHistory } = require('./History')

const command_matches ={
    "!背包":"GetInventory",
    "!物品":"GetItemInHand",
    "!状态":"GetState",
    "!坐标":"GetPosition",
    "!附近实体":"GetAroundEntities",
}


function matchCommand(input) {
    return command_matches[input.trim()] || null
}


async function processCommand(bot, input) {
    const toolName = matchCommand(input)
    if (!toolName) {
        bot.chat(`未知指令: ${input}, 可用指令包括: ${Object.keys(command_matches).join(', ')}`)
        return
    }
    addToHistory("system", `执行快捷指令： ${input}`)
    const action = { name: toolName, args: {} }

    try {
        const result = await ExecuteAction(bot, action)
        bot.chat(result.message)
        await TaskCompleteCheck(bot, true, result.message, '没有下一步动作，整体任务已完成。')
    } catch (err) {
        bot.chat(`快捷指令 ${input} 执行失败: ${err.message}`)
        await TaskCompleteCheck(bot, false, err.message, '请回复 yes 重试')
    }
}

module.exports = {
    command_matches,
    processCommand,
}



