/**
 * 工具：GetItemInHand — 查询手持物品
 */
module.exports = {
  name: "GetItemInHand",
  args: [],
  class: "QueryTools",
  description: "Query what the bot is currently holding — use when a player asks 'what are you holding', 'what's in your hand', 'what item do you have', or 'show me your hand'. Returns item name, count, and whether it's a block.",

  execute(bot) {
    const item = bot.heldItem?.name || '空手'
    const count = bot.heldItem?.count || 0
    if (item === '空手') {
      return { message: `bot手上没有物品` }
    }
    return { message: `bot手上是: ${item}, 数量为: ${count}` }
  }
}
