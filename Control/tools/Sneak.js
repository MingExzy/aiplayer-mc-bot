/**
 * 工具：Sneak — 切换潜行
 */
module.exports = {
  name: "Sneak",
  args: ["state"],
  class: "BasicControlTools",
  description: "Toggle sneaking/crouching mode — use when a player says 'sneak', 'crouch', 'stealth mode', or 'go quietly'. state can be 'on' (start sneaking) or 'off' (stop sneaking).",

  execute(bot, args) {
    if (args.state === "on") {
      bot.setControlState('sneak', true)
      return { message: 'bot开始潜行' }
    }
    bot.setControlState('sneak', false)
    return { message: 'bot停止潜行' }
  }
}
