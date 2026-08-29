/**
 * 聊天历史（进程内内存，最大 50 条）
 * （原 History.js）
 *
 * 职责：以 {role, content, ts} 结构维护本次对话历史，供规划 / 反思 / 保存技能时传给 Python 层。
 */

let ChatHistory = []

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



module.exports = {
    addToHistory,
    getHistory,
    clearHistory,
}
