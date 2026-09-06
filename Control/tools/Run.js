/**
 * 工具：run — 切换疾跑
 */
module.exports = {
  name: "run",
  args: [
    { name: "state", type: "string", required: true, enum: ["on", "off"] }
  ],
  class: "BasicControlTools",
  description: "Toggle running/sprinting/dashing mode — use when a player says 'run', 'sprint', 'dash', 'go faster', or 'speed up'. state can be 'on' (start sprinting) or 'off' (stop sprinting).",

  execute(bot, args) {
    if (args.state === "on") {
      bot.setControlState('sprint', true)
      return { message: 'bot开启疾跑模式' }
    }
    bot.setControlState('sprint', false)
    return { message: 'bot停止疾跑模式' }
  }
}
