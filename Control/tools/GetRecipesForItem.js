/**
 * 工具：GetRecipesForItem — 查询合成配方
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "GetRecipesForItem",
  args: [
    { name: "item", type: "string", required: true }
  ],
  class: "QueryTools",
  description: "Query how to craft/make/create an item — use when a player asks 'how to make', 'how to craft', 'recipe for', 'crafting recipe of', 'how do I create', 'make' ,or  'craft' an item. item is the name of the item (e.g. 'diamond_sword', 'pickaxe'). Returns the crafting recipe if it's a craftable item.",

  execute(bot, args) {
    const itemID = mcData.itemsByName[args.item]?.id
    if (!itemID) {
      throw new Error(`未知的物品: ${args.item}`)
    }
    const recipes = bot.recipesFor(itemID, null, 1, null)
    if (recipes.length === 0) {
      throw new Error(`无法制作${args.item}，没有找到相关配方`)
    }
    return { message: `${args.item}的制作配方有: ${JSON.stringify(recipes)}` }
  }
}
