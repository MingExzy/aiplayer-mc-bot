/**
 * 工具：ThrowItems — 从背包丢弃物品
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "ThrowItems",
  args: ["item", "count"],
  class: "ItemControlTools",
  description: "Throw/drop/toss/discard items from your inventory — use when a player says 'throw', 'drop', 'toss', 'discard', or 'get rid of'. item is the name of the item to throw, count is how many to throw, default is 1.",

  async execute(bot, args) {
    try {
      const itemId = mcData.itemsByName[args.item]?.id
      if (!itemId) {
        throw new Error(`未知的物品: ${args.item}`)
      }

      const itemObj = bot.inventory.items().find(item => item.type === itemId)
      if (!itemObj) {
        throw new Error('背包里面没有这个物品')
      }
      const itemCount = Math.min(itemObj.count, args.count || 1)
      await bot.toss(itemObj.type, null, itemCount)
      return { message: `bot已丢弃手中的物品` }
    } catch (error) {
      throw new Error(`丢弃手中的物品时出错: ${error.message}`)
    }
  }
}
