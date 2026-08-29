/**
 * 工具：Turn — 转头到指定朝向
 */
module.exports = {
  name: "Turn",
  args: ["yaw", "pitch"],
  class: "BasicControlTools",
  description: "Turn/rotate the bot's head to face a specific direction — use when a player says 'turn left/right', 'look south/west', 'face me', 'turn around', or 'look up/down'. yaw: -PI to PI (0=south, PI/2=west); pitch: -PI/2 to PI/2 (0=horizon, -PI/2=up, PI/2=down).",

  async execute(bot, args) {
    await bot.look(args.yaw, args.pitch)
    return { message: `bot成功转向` }
  }
}
