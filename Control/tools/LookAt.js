/**
 * 工具：LookAt — 看向指定坐标
 */
const Vec3 = require('vec3')

module.exports = {
  name: "LookAt",
  args: [
    { name: "x", type: "number", required: true },
    { name: "y", type: "number", required: true },
    { name: "z", type: "number", required: true }
  ],
  class: "BasicControlTools",
  description: "Look/stare/face towards a specific coordinate position — use when a player tells you to 'look at', 'stare at', or 'face towards' a location. x, y, z are the target coordinates.",

  async execute(bot, args) {
    await bot.lookAt(new Vec3(args.x, args.y, args.z))
    return { message: `bot已看向(${args.x}, ${args.y}, ${args.z})` }
  }
}
