/**
 * 工具：FollowPlayer — 跟随 / 停止跟随玩家
 */
const { goals: { GoalFollow } } = require('mineflayer-pathfinder')

module.exports = {
  name: "FollowPlayer",
  args: ["playerName", "state"],
  class: "AdvancedControlTools",
  description: "Follow/chase/stalk a specific player — use when a player says 'follow me', 'follow {playerName}', 'chase {playerName}', 'stalk {playerName}', or 'come with me'. playerName is the name of the player to follow. State can be 'on' (start following) or 'off' (stop following).",

  execute(bot, args) {
    const player = bot.players[args.playerName]
    if (!player || !player.entity) {
      throw new Error(`找不到玩家${args.playerName}，无法跟随`)
    }
    if (args.state === "on") {
      const goal = new GoalFollow(player.entity, 2)
      bot.pathfinder.setGoal(goal, true)
      return { message: `bot正在跟随玩家${args.playerName}` }
    }
    bot.pathfinder.setGoal(null)
    return { message: `bot停止跟随玩家${args.playerName}` }
  }
}
