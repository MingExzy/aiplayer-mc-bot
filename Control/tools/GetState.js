/**
 * 工具：GetState — 查询血量、饱食度、坐标
 */


module.exports = {
  name: "GetState",
  args: [],
  class: "QueryTools",
  description: "Query the bot's current status — use when a player asks 'how are you', 'your health', 'your status', 'where are you', 'coords', 'coordinates', 'how much health', 'your hunger', 'are you okay', or 'condition'. Returns health, hunger, and current coordinates (x,y,z).",

  execute(bot) {
    const pos = bot.entity?.position
    const coords = pos ? `坐标 (${pos.x.toFixed(1)}, ${pos.y.toFixed(1)}, ${pos.z.toFixed(1)})` : '坐标未知'
    return { message: `bot血量: ${bot.health}, 饱食度: ${bot.food}, ${coords}` }
  }
}
