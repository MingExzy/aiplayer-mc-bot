/**
 * 工具：PlaceBlock — 在指定位置放置方块
 */
const Vec3 = require('vec3')
const mcData = require('minecraft-data')('1.21.1')

module.exports = {
  name: "PlaceBlock",
  args: [
    { name: "block", type: "string", required: true },
    { name: "x", type: "number", required: true },
    { name: "y", type: "number", required: true },
    { name: "z", type: "number", required: true }
  ],
  class: "InteractWithBlockTools",
  description: "Place/put/build/set down a block at a specific position — use when a player says 'place', 'put', 'build', 'set down', or 'put a block at'. Checks inventory first, then equips and places. block is the block name, x/y/z are coordinates.",

  async execute(bot, args) {
    const { block, x, y, z } = args
    const blockId = mcData.itemsByName[block]?.id
    if (!blockId) {
      throw new Error(`未知的方块类型: ${block}`)
    }
    await bot.equip(blockId, 'hand')
    const referenceBlock = bot.blockAt(new Vec3(x, y, z))
    const targetPosition = [x, y, z].some(Number.isNaN) ? null : new Vec3(x, y, z)
    if (!targetPosition) {
      throw new Error(`无效的坐标: (${x}, ${y}, ${z})`)
    }
    if (referenceBlock.name !== 'air' && referenceBlock.name !== 'water') {
      throw new Error(`目标位置(${x}, ${y}, ${z})上有一个${referenceBlock.name}方块，无法放置`)
    }

    const candidates = [
      { offset: new Vec3(0, -1, 0), faceVector: new Vec3(0, 1, 0) },
      { offset: new Vec3(0, 1, 0), faceVector: new Vec3(0, -1, 0) },
      { offset: new Vec3(1, 0, 0), faceVector: new Vec3(-1, 0, 0) },
      { offset: new Vec3(-1, 0, 0), faceVector: new Vec3(1, 0, 0) },
      { offset: new Vec3(0, 0, 1), faceVector: new Vec3(0, 0, -1) },
      { offset: new Vec3(0, 0, -1), faceVector: new Vec3(0, 0, 1) }
    ]

    for (const candidate of candidates) {
      const referencePosition = targetPosition.plus(candidate.offset)
      const refBlock = bot.blockAt(referencePosition)
      if (refBlock && refBlock.name !== 'air' && refBlock.name !== 'water') {
        await bot.placeBlock(refBlock, candidate.faceVector)
        return { message: `bot已在(${x}, ${y}, ${z})放置${block}方块` }
      }
    }
    throw new Error(`无法在(${x}, ${y}, ${z})放置${block}方块，因为周围没有可用的参考方块`)
  }
}
