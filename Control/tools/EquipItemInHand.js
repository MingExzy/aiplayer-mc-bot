/**
 * 工具：EquipItemInHand — 装备物品到手上
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "EquipItemInHand",
  args: [
    { name: "item", type: "string", required: true }
  ],
  class: "ItemControlTools",
  description: "Equip/wield/hold/take out an item from your inventory into your hand — use when a player says 'equip', 'hold', 'take out', 'wield', 'grab', or 'get your {item}'. item is the name of the item to equip (e.g. 'diamond_sword', 'pickaxe').",

  async execute(bot, args) {
    try {
      const itemId = mcData.itemsByName[args.item].id
      if (!itemId) {
        throw new Error(`未知的物品: ${args.item}`)
      }
      await bot.equip(itemId, 'hand')
      return { message: `bot已装备物品${args.item}` }
    } catch (error) {
      throw new Error(`装备物品${args.item}时出错: ${error.message}`)
    }
  }
}
