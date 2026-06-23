const { initBot } = require('./Bot')
const { initMCPSession, requestTaskPlan,handleMessage } = require('./MCP')
const { } = require('./BotTools')
const {addToHistory,loadHistoryFromFile, setWorldPath} = require('./History')
const { processCommand } = require('./rules')
const fs = require('fs')
const path = require('path')
const rl = require('readline').createInterface({
    input: process.stdin,
    output: process.stdout
})


let Bot = null


async function ask(question) {
    return new Promise((resolve) => {
        rl.question(question, (answer) => {
            resolve(answer);
        });
    });
}



async function chooseWorldBackground(){
    worlds_path = "../"
    const projectDir = path.basename(process.cwd())
    const worlds = fs.readdirSync(worlds_path).filter(f => {
        if (f === projectDir) return false
        try { return fs.statSync(path.resolve(worlds_path, f)).isDirectory() }
        catch { return false }
    })
    console.log("当前版本下的存档列表：")
    console.log(worlds)
    while (true) {
        const choice = await ask("请在上方列表中输入要加载的存档名称的索引（从上到下，从 0 开始）：")
        const index = parseInt(choice)
        if (isNaN(index) || index < 0 || index >= worlds.length) {
            console.log("输入无效，请输入正确的索引编号。")
            continue
        }
        const selected = worlds[index]
        const fullPath = path.resolve(worlds_path, selected)
        if (!fs.statSync(fullPath).isDirectory()) {
            console.log(`"${selected}" 不是有效的存档文件夹，请重新选择。`)
            continue
        }
        return selected
    }
}


async function main() {
    const world = await chooseWorldBackground()
    console.log(`你选择了存档：${world}，正在启动 Bot...`)
    history_path = path.join(world, "history.json")
    setWorldPath(history_path)
    await loadHistoryFromFile(history_path)
    Bot = initBot('AIPlayer')
    console.log('Bot 启动，等待 spawn 事件以初始化 MCP session。')

    rl.on('line', (input) => {
        if (input.startsWith('!') && Bot) {
            processCommand(Bot, input)
        }
    })
}

main()