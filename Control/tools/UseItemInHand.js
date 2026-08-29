/**
 * 工具：UseItemInHand — 使用手中的物品
 */
module.exports = {
  name: "UseItemInHand",
  args: [],
  class: "ItemControlTools",
  description: "Use/activate/interact with the item currently in your hand — use when a player says 'use', 'activate', 'right-click', or 'interact' with your held item.",

  async execute(bot) {
    try {
      await bot.activateItem()
      await bot.deactivateItem()
      return { message: `bot已使用手中的物品` }
    } catch (error) {
      throw new Error(`使用手中的物品时出错: ${error.message}`)
    }
  }
}
