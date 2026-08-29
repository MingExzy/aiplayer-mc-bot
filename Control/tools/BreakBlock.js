/**
 * 工具：BreakBlock — 破坏指定位置的方块
 */
const Vec3 = require('vec3')

module.exports = {
  name: "BreakBlock",
  args: ["x", "y", "z"],
  class: "InteractWithBlockTools",
  description: "Break/mine/dig/destroy/remove a block at a specific position — use when a player says 'break', 'mine', 'dig', 'destroy', 'remove', or 'knock down' a block. x, y, z are the target coordinates.",

  async execute(bot, args) {
    const block = bot.blockAt(new Vec3(args.x, args.y, args.z))
    if (!block || block.name === 'air' || block.name === 'water') {
      throw new Error(`目标位置(${args.x}, ${args.y}, ${args.z})上没有可破坏的方块`)
    }
    await bot.dig(block)
    return { message: `bot已破坏(${args.x}, ${args.y}, ${args.z})处的${block.name}方块` }
  }
}
