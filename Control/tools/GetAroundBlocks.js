/**
 * 工具：GetAroundBlocks — 查询周围小部分的指定方块
 */
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "GetAroundBlocks",
  args: [],
  class: "QueryTools",
  description: "Find/locate/search for the blocks around the bot within 16 blocks — use when a player asks 'blocks around you', 'Around you', 'what blocks are near you', or 'show me the blocks around me'. Returns a list of blocks and their coordinates (x,y,z).",

  execute(bot) {
    const radius = 3
    const pos = bot.entity?.position
    const block_list = []
    if (!pos) {
      throw new Error('无法获取bot的位置')
    }
    for (let x = -radius; x <= radius; x++) {
      for (let z = -radius; z <= radius; z++) {
        for (let y = -radius; y <= radius; y++) {
            const block = bot.blockAt(pos.offset(x, y, z))
            if (block && block.name !== 'air') {
                block_list.push({ name: block.name, x: block.position.x, y: block.position.y, z: block.position.z })
            }
        }
      }
    }
    if (block_list.length === 0) {
      throw new Error(`在${radius}个方块内没有找到任何方块`)
    }
    return { message: `附近的方块: ${JSON.stringify(block_list)}` }
  }
}
