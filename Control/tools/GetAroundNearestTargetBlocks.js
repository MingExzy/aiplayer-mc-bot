/**
 * 工具：GetAroundNearestTargetBlocks — 搜索最近的指定方块
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "GetAroundNearestTargetBlocks",
  args: [
    { name: "targetBlock", type: "string", required: true }
  ],
  class: "QueryTools",
  description: "Find/locate/search for the nearest blocks of a specific type within 32 blocks radius of the bot — use when a player asks 'find', 'locate', 'look for', 'where is', 'any {block} nearby', 'find me {block}', or 'search for {block}'. targetBlock is the block name (e.g. 'diamond_ore', 'iron_ore', 'tree').",

  execute(bot, args) {
    const radius = 32
    const blockID = mcData.blocksByName[args.targetBlock]?.id
    if (!blockID) {
      throw new Error(`未知的方块类型: ${args.targetBlock}`)
    }
    const blocks = bot.findBlocks({
      matching: blockID,
      maxDistance: radius,
      count: 10
    })
    if (blocks.length === 0) {
      throw new Error(`在${radius}个方块内没有找到${args.targetBlock}方块`)
    }
    return { message: `最近的 ${args.targetBlock} 方块: ${JSON.stringify(blocks)}` }
  }
}
