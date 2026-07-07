const fs = require('fs');
const path = require('path');

let ChatHistory = []
let _worldHistoryPath = null
const MAX_HISTORY = 50



function addToHistory(role, message) {

    if (ChatHistory.length >= MAX_HISTORY) {
        ChatHistory.shift() // Remove the oldest message
    }
    ChatHistory.push({"role": role, "content": message, "ts": Math.floor(Date.now() / 1000)})
}

function getHistory() {
    return ChatHistory
}

function clearHistory() {
    ChatHistory = []
}

async function loadHistoryFromFile(filePath) {
    try{
        if (fs.existsSync(filePath)) {
            const data = fs.readFileSync(filePath, 'utf-8')
            const savedMsg = JSON.parse(data).message
            addToHistory("system", `历史记录已加载: ${savedMsg}`)
            console.log(`历史记录已从 ${filePath} 加载`)
        }
        else{
            console.log(`历史记录文件 ${filePath} 不存在，正在创建新的历史记录文件。`)
            fs.writeFileSync(filePath, JSON.stringify({message: ""}), 'utf-8')
            console.log(`新的历史记录文件 ${filePath} 已创建`)
        }
    } catch (error) {
        console.error(`加载历史记录时出错 [路径: ${filePath}]: ${error.message}`)
    }
}


async function saveHistoryToFile(filePath, message) {
    try {
        const data = JSON.stringify({ message });
        fs.writeFileSync(filePath, data, 'utf-8');
        console.log(`历史记录已保存到 ${filePath}`);
    } catch (error) {
        console.error(`保存历史记录时出错 [路径: ${filePath}]: ${error.message}`);
    }
}


function setWorldPath(filePath) {
    _worldHistoryPath = filePath
}

function getWorldPath() {
    return _worldHistoryPath
}


module.exports = {
    addToHistory,
    getHistory,
    clearHistory,
    loadHistoryFromFile,
    saveHistoryToFile,
    setWorldPath,
    getWorldPath,
}
