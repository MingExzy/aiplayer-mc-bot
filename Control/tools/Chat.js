/**
 * 工具：Chat — 发送聊天消息
 */
const { addToHistory } = require('../bot/history')

module.exports = {
  name: "Chat",
  args: ["message"],
  class: "InteractWithPlayerTools",
  description: "Send a chat message to players — use when you want to talk, say, speak, reply, respond, or tell something to other players. message is the text content of the chat.",

  execute(bot, args) {
    bot.chat(args.message)
    addToHistory("bot", `${args.message}`)
    return { message: `已发送聊天: ${args.message}` }
  }
}
