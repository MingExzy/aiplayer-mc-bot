const mineflayer = require('mineflayer')
const { pathfinder, Movements, goals: { GoalBlock } } = require('mineflayer-pathfinder')
const Vec3 = require('vec3')
const fs = require('fs')
const path = require('path')
const { addToHistory, getWorldPath } = require('./History')
const { initMCPSession, requestTaskPlan, handleMessage } = require('./MCP')

const { normalizeActionList } = require('./user_utils')
const {command_matches,processCommand} = require('./rules')

let bot = null



function initBot(botname) {
    // 初始化 Mineflayer 机器人，并挂载路径寻路插件。
    bot = mineflayer.createBot({
    host: 'localhost', // minecraft 服务器的 IP 地址
    username: botname, // minecraft 用户名
    // password: '12345678' 
    // port: 25565,
    version: '1.21.1'
    // auth: 'mojang'
    })

    bot.loadPlugin(pathfinder)

    bot.on('spawn', async () => {
        const defaultMove = new Movements(bot)
        bot.pathfinder.setMovements(defaultMove)
        console.log('Bot 已生成，路径寻路插件已加载。')
        try {
            await initMCPSession()
            console.log('MCP session initialized from Bot.spawn')
        } catch (err) {
            console.error('初始化 MCP session 失败:', err)
        }
    })

    bot.on('chat', async (username, message) => {
        if (username === bot.username) return
        addToHistory('player', `${username}: ${message}`)
        bot.chat(`思考中...`)
        let keepPlanning = true
        let activeSkillProgress = null
        while (keepPlanning) {
            try {
                // 根据玩家消息分类工具集并请求计划
                const rawPlan = await requestTaskPlan(username, message, activeSkillProgress)
                const actions = normalizeActionList(rawPlan)
                const shouldContinue = rawPlan?.continue === true
                activeSkillProgress = rawPlan?.skillProgress || null

                // 执行动作
                const result = await handleMessage(bot, actions)
                if (shouldContinue && result?.success) {
                    addToHistory("system", `当前动作序列执行完毕，继续任务，再次明确用户${username}需求：${message}`)
                }
                else if (result?.success) {
                    addToHistory("system", `整体任务已完成`)
                    break
                }
                else {
                    // 失败信息已由 TaskCompleteCheck 写入历史，直接退出
                    break
                }

            } catch (err) {
                console.error('处理聊天消息失败:', err)
                // 异常信息已在 MCP/执行层记录，直接退出
                break
            }
        }
    })
    bot.on('error', err => console.error('机器人错误:', err))
    bot.on('end', async (reason) => {
        console.log('Bot 断开:', reason)
        try {
            const historyPath = getWorldPath()
            if (historyPath) {
                console.log('正在保存会话记忆...')
                const { getHistory, saveHistoryToFile } = require('./History')
                const { requestSummary } = require('./MCP')
                const summary = await requestSummary(getHistory())
                saveHistoryToFile(historyPath, summary)
                console.log('会话记忆已保存')
            }
        } catch (err) {
            console.error('保存记忆失败:', err.message)
        }
        console.log('Bot 已退出。')
    })
    bot.on('kicked', console.log)

    return bot
}

module.exports = {
    initBot,
}