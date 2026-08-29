/**
 * 工具：CraftItem — 合成物品（必要时使用工作台）
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "CraftItem",
  args: ["item", "count"],
  class: "AdvancedControlTools",
  description: "Craft/make/create items without using the crafting table — use when a player says 'craft', 'make', 'create', or 'build' an item. item is the name of the item to craft (e.g. 'diamond_sword', 'pickaxe'); count is how many to craft (integer >= 0).",

  async execute(bot, args) {
    try {
      const recipe = bot.recipesFor(mcData.itemsByName[args.item].id, null, 1, null)[0]
      if (!recipe) {
        throw new Error(`无法制作${args.item}，没有找到相关配方`)
      }
      const needTable = recipe.requiresTable
      if (needTable) {
        const craftingTableBlock = bot.findBlock({
          matching: mcData.blocksByName.crafting_table.id,
          maxDistance: 2
        })
        if (!craftingTableBlock) {
          bot.chat("我需要一个工作台来做这个，但我旁边没有")
          throw new Error('bot附近没有工作台，无法制作需要工作台的物品')
        }
        try {
          await bot.craft(recipe, args.count, craftingTableBlock)
          bot.chat("我用工作台做完了这个东西！")
          return { message: `bot已制作${args.count}个${args.item}，使用了工作台` }
        } catch (error) {
          throw new Error(`制作${args.item}失败: ${error.message}`)
        }
      } else {
        try {
          await bot.craft(recipe, args.count)
          bot.chat("我做完了这个东西！")
          return { message: `bot已制作${args.count}个${args.item}，没有使用工作台` }
        } catch (error) {
          throw new Error(`制作${args.item}失败: ${error.message}`)
        }
      }
    } catch (error) {
      throw new Error(`制作${args.item}失败: ${error.message}`)
    }
  }
}
