/**
 * 工具：Jump — 持续跳跃
 */
const { addToHistory } = require('../bot/history')

module.exports = {
  name: "Jump",
  args: [
    { name: "lastTime", type: "integer", required: false }
  ],
  class: "BasicControlTools",
  description: "Make the bot jump, hop, or leap — use when a player says 'jump', 'jump up', 'hop', or 'leap over something'. lastTime is the duration of the jump in milliseconds，default is 5000.",

  execute(bot, args) {
    const lastTime = args.lastTime || 5000
    addToHistory("bot", `我将保持跳跃${lastTime / 1000}秒`)
    bot.setControlState('jump', true)
    setTimeout(() => {
      bot.setControlState('jump', false)
      addToHistory("bot", `我已停止跳跃`)
    }, lastTime)
    return { message: `bot进行了持续${lastTime / 1000}秒的跳跃` }
  }
}
