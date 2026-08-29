/**
 * 工具：GetAroundEntities — 扫描周围实体
 */
module.exports = {
  name: "GetAroundEntities",
  args: [],
  class: "QueryTools",
  description: "Query what's nearby the bot — use when a player asks 'what's around you', 'nearby entities', 'who's nearby', 'what do you see', 'are there any mobs', 'any players nearby', or 'scan surroundings'.",

  execute(bot) {
    const radius = 32
    const nearby = []
    const botPos = bot.entity.position
    for (const id in bot.entities) {
      const entity = bot.entities[id]
      if (entity === bot.entity) continue // 排除自己
      const distance = entity.position.distanceTo(botPos)
      if (distance <= radius) {
        nearby.push({ entity, distance })
      }
    }
    nearby.sort((a, b) => a.distance - b.distance)
    return { message: `bot周边实体有: ${JSON.stringify(nearby)}` }
  }
}
