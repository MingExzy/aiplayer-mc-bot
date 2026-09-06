/**
 * 工具：Move — 朝某个方向移动指定格数
 */
module.exports = {
  name: "Move",
  args: [
    { name: "direction", type: "string", required: true, enum: ["forward", "backward", "left", "right"] },
    { name: "blocks", type: "integer", required: true }
  ],
  class: "BasicControlTools",
  description: "Move/walk/go in a direction for a certain number of blocks — use when a player tells you to move forward, backward, left, or right. direction must be forward, backward, left, or right; blocks must be an integer >= 0.",

  execute(bot, args) {
    const direction = args.direction
    const block = args.blocks
    const timeOut = 10000
    const startPosition = bot.entity.position.clone()
    bot.setControlState(direction, true)

    return new Promise((resolve, reject) => {
      const startTime = Date.now()
      const interval = setInterval(() => {
        const distance = bot.entity.position.distanceTo(startPosition)
        if (distance >= block) {
          bot.setControlState(direction, false)
          clearInterval(interval)
          resolve({ message: `成功往${direction}移动${block}格` })
          return
        } else if (Date.now() - startTime > timeOut) {
          bot.setControlState(direction, false)
          clearInterval(interval)
          reject(new Error('移动超时！'))
        }
      }, 100)
    })
  }
}
