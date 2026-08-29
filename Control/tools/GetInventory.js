/**
 * 工具：GetInventory — 查询背包
 */
module.exports = {
  name: "GetInventory",
  args: [],
  class: "QueryTools",
  description: "Query what the bot is carrying — use when a player asks 'what do you have', 'your items', 'your inventory', 'what's in your inventory', 'what are you carrying', or 'show me your items'.",

  execute(bot) {
    return { message: `bot的背包物品为: ${JSON.stringify(bot.inventory)}` }
  }
}
