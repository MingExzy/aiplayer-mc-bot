/**
 * 工具：MoveTo — 寻路到指定坐标
 */
const { goals: { GoalBlock } } = require('mineflayer-pathfinder')

module.exports = {
  name: "MoveTo",
  args: [
    { name: "x", type: "number", required: true },
    { name: "y", type: "number", required: true },
    { name: "z", type: "number", required: true }
  ],
  class: "BasicControlTools",
  description: "Walk/go/travel/pathfind to a specific coordinate location — use when a player says 'go to', 'walk to', 'head to', 'travel to', or 'come to' a certain place. x, y, z are the target coordinates.",

  async execute(bot, args) {
    await bot.pathfinder.goto(new GoalBlock(Number(args.x), Number(args.y), Number(args.z)))
    return { message: `bot已移动到(${args.x}, ${args.y}, ${args.z})` }
  }
}
