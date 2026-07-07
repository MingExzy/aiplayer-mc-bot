const { pathfinder, Movements, goals: { GoalBlock, GoalFollow } } = require('mineflayer-pathfinder')
const Vec3 = require('vec3')
const { addToHistory,getHistory } = require('./History')
const mcData = require('minecraft-data')(mcDataVersion = '1.21.1')
const config = require('./config.json')
const { extractJsonFromSSE } = require('./user_utils')
/// bot = function createBot() {
  // 初始化 Mineflayer 机器人，并挂载路径寻路插件。
  //bot = mineflayer.createBot({
    //host: 'localhost', // minecraft 服务器的 IP 地址
    //username: 'example', // minecraft 用户名
    // password: '12345678' 
    // port: 25565,
    // version: false,
    // auth: 'mojang'
 // })

const tools = require('./tools.json')



async function SaveSkill(Bot,skill_name) {
    if (typeof fetch !== 'function') {
    throw new Error('当前运行环境不支持 fetch')
  }

  // 发给 MCP 的 payload 也是标准 JSON，history 会保留前面统一好的消息结构。
  const response = await fetch(config.mcp_url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
      'Mcp-Session-Id': config.mcp_session_id
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'tools/call',
      params: {
        name: 'saveSkill',
        arguments: {
          chatHistory: getHistory(),
          skill_name: skill_name
        }
      },
      id:3,
    }),
    signal: AbortSignal.timeout(30000)
  })

  console.log('发送给 saveSkill 的参数:', JSON.stringify({ chatHistory: getHistory(), skill_name }, null, 2));
  const text = await response.text()
  if (!response.ok) {
    throw new Error(`MCP 服务器返回 ${response.status}: ${text}`)
  }

  const data = extractJsonFromSSE(text)
  const resultText = data.result?.content?.[0]?.text || ''
  if (resultText.startsWith('技能保存失败')) {
    throw new Error(resultText)
  }
  Bot.chat(resultText)
  addToHistory("system", resultText)
}
// const AdvancedControlTools = [
//     {name:"BuildPillar", args:["Block","bottomIndex","height"], class:"AdvancedControlTools",
//         description: "Build a pillar with specific block type, bottomIndex is the index of the bottom block: 0-8, [[0,1,2],[3,4,5],[6,7,8]], 4 is the bottom block of the bot. cannot build above the bot, height is the height of the pillar, less than 3"},
// ]

function GetBotTools(){
    return tools
}



function normalizeToolName(name) {
  return String(name || '').trim()
}

function normalizeArgs(args) {
  if (!args) {
    return {}
  }

  if (typeof args === 'string') {
    try {
      return JSON.parse(args)
    } catch (_) {
      return { value: args }
    }
  }
  return args
}

function Move(Bot, direction, block, timeOut = 10000) {
    const startPosition = Bot.entity.position.clone()
    Bot.setControlState(direction, true)

    return new Promise((resolve, reject) => {
        const startTime = Date.now()
        const interval = setInterval(() => {
            const distance = Bot.entity.position.distanceTo(startPosition)
            if (distance >= block) {
                Bot.setControlState(direction, false)
                clearInterval(interval)
                resolve({ message: `成功往${direction}移动${block}格` })
                return
            }
            else if (Date.now() - startTime > timeOut) {
                Bot.setControlState(direction, false)
                clearInterval(interval)
                reject(new Error('移动超时！'))
            }
        }, 100)
    })
}


function Jump(Bot,lastTime = 5000) {
    addToHistory("bot", `我将保持跳跃${lastTime/1000}秒`)
    Bot.setControlState('jump', true)
    setTimeout(() => {
        Bot.setControlState('jump', false)
        addToHistory("bot", `我已停止跳跃`)
    }, lastTime)
    return { message: `bot进行了持续${lastTime/1000}秒的跳跃` }
}

async function Turn(Bot, yaw, pitch) {
    await Bot.look(yaw, pitch)
    return { message: `bot成功转向` }
}

function Sneak(Bot, state) {
    if (state === "on") {
        Bot.setControlState('sneak', true)
        return { message: 'bot开始潜行' }
    } else {
        Bot.setControlState('sneak', false)
        return { message: 'bot停止潜行' }
    }
}

function Run(Bot, state) {
    if (state === "on") {
        Bot.setControlState('sprint', true)
        return { message: 'bot开启疾跑模式' }
    } else {
        Bot.setControlState('sprint', false)
        return { message: 'bot停止疾跑模式' }
    }
}

async function LookAt(Bot, x, y, z) {
    await Bot.lookAt(new Vec3(x, y, z))
    return { message: `bot已看向(${x}, ${y}, ${z})` }
}

async function MoveTo(Bot, x, y, z) {
    await Bot.pathfinder.goto(new GoalBlock(Number(x), Number(y), Number(z)))
    return { message: `bot已移动到(${x}, ${y}, ${z})` }
}

async function EquipItemInHand(Bot, item) {
    try {
        const itemId = mcData.itemsByName[item].id
        if (!itemId) {
            throw new Error(`未知的物品: ${item}`)
        }
        await Bot.equip(itemId, 'hand')
        return { message: `bot已装备物品${item}` }
    } catch (error) {
        throw new Error(`装备物品${item}时出错: ${error.message}`)
    }
}

async function UseItemInHand(Bot) {
    try {
        await Bot.activateItem()
        await Bot.deactivateItem()
        return { message: `bot已使用手中的物品` }
    } catch (error) {
        throw new Error(`使用手中的物品时出错: ${error.message}`)
    }
}

async function ThrowItems(Bot,item_name,count=1) {
    try {
        const itemId = mcData.itemsByName[item_name]?.id
        if (!itemId) {
            throw new Error(`未知的物品: ${item_name}`)
        }

        const itemObj = Bot.inventory.items().find(item => item.type === itemId)
        if (!itemObj) {
            throw new Error('背包里面没有这个物品')
        }
        const itemCount = Math.min(itemObj.count, count)
        await Bot.toss(itemObj.type, null,itemCount)
        return { message: `bot已丢弃手中的物品` }
    } catch (error) {
        throw new Error(`丢弃手中的物品时出错: ${error.message}`)
    }
}

async function PlaceBlock(Bot, block, x, y, z) {
    const blockId = mcData.itemsByName[block]?.id
    if (!blockId) {
        throw new Error(`未知的方块类型: ${block}`)
    }
    await Bot.equip(blockId, 'hand')
    const referenceBlock = Bot.blockAt(new Vec3(x, y, z))
    const targetPosition = [x, y, z].some(Number.isNaN) ? null : new Vec3(x, y, z)
    if (!targetPosition) {
        throw new Error(`无效的坐标: (${x}, ${y}, ${z})`)
    }
    if (referenceBlock.name !== 'air' && referenceBlock.name !== 'water' ) {
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
        const referenceBlock = Bot.blockAt(referencePosition)

        if (referenceBlock && referenceBlock.name !== 'air' && referenceBlock.name !== 'water') {
                await Bot.placeBlock(referenceBlock, candidate.faceVector)
                return { message: `bot已在(${x}, ${y}, ${z})放置${block}方块` }
        }
    }
    throw new Error(`无法在(${x}, ${y}, ${z})放置${block}方块，因为周围没有可用的参考方块`)
}

async function BreakBlock(Bot, x, y, z, timeOut = 30000) {
    const block = Bot.blockAt(new Vec3(x, y, z))
    if (!block || block.name === 'air'|| block.name === 'water') {
        throw new Error(`目标位置(${x}, ${y}, ${z})上没有可破坏的方块`)
    }
    await Bot.dig(block)
    return { message: `bot已破坏(${x}, ${y}, ${z})处的${block.name}方块` }
}

async function GetPosition(Bot) {
    const position = Bot.entity.position
    return { message: `bot位置: (${position.x.toFixed(2)}, ${position.y.toFixed(2)}, ${position.z.toFixed(2)})` }
}

function GetState(Bot) {
    const health = Bot.health
    const food = Bot.food
    return { message: `bot血量: ${health}, 饱食度: ${food}` }
}

function GetInventory(Bot) {
    const inventory = Bot.inventory
    return { message: `bot的背包物品为: ${JSON.stringify(inventory)}` }
}

function GetItemInHand(Bot) {
    const item = Bot.heldItem?.name || '空手'
    const count = Bot.heldItem?.count || 0
    if (item === '空手') {
        return { message: `bot手上没有物品` }
    }
    return { message: `bot手上是: ${item}, 数量为: ${count}` }
}

function GetAroundEntities(Bot, radius = 32) {
    const nearby = []
    const botPos = Bot.entity.position
    for (const id in Bot.entities) {
        const entity = Bot.entities[id]
        if (entity === Bot.entity) continue  // 排除自己
        const distance = entity.position.distanceTo(botPos)
        if (distance <= radius) {
            nearby.push({ entity, distance })
        }
    }
    nearby.sort((a, b) => a.distance - b.distance)
    return { message: `bot周边实体有: ${JSON.stringify(nearby)}` }
}

function GetAroundNearestTargetBlocks(Bot, targetBlock, radius = 32) {
    const blockID = mcData.blocksByName[targetBlock]?.id
    if (!blockID) {
        throw new Error(`未知的方块类型: ${targetBlock}`)
    }
    const nearby = []
    const botPos = Bot.entity.position
    const blocks = Bot.findBlocks({
        matching: blockID,
        maxDistance: radius,
        count: 10
    })
    if (blocks.length === 0) {
        throw new Error(`在${radius}个方块内没有找到${targetBlock}方块`)
    }
    return { message: `最近的 ${targetBlock} 方块: ${JSON.stringify(blocks)}` }
}

function GetRecipesForItem(Bot, item) {
    const itemID = mcData.itemsByName[item]?.id
    if (!itemID) {
        throw new Error(`未知的物品: ${item}`)
    }
    const recipes = Bot.recipesFor(itemID, null,1, null)
    if (recipes.length === 0) {
        throw new Error(`无法制作${item}，没有找到相关配方`)
    }
    return { message: `${item}的制作配方有: ${JSON.stringify(recipes)}` }
}


async function FollowPlayer(Bot, playerName,state) {
    const player = Bot.players[playerName]
    if (!player || !player.entity) {
        throw new Error(`找不到玩家${playerName}，无法跟随`)
    }
    if (state === "on"){
        const goal = new GoalFollow(player.entity, 2) // 跟随目标玩家，保持1格距离
        Bot.pathfinder.setGoal(goal,true)
        return { message: `bot正在跟随玩家${playerName}` }
    }
    else{
        Bot.pathfinder.setGoal(null) // 取消跟随
        return { message: `bot停止跟随玩家${playerName}` }
    }
}

async function CraftItem(Bot, item, count) {
    try {
        const recipe = Bot.recipesFor(mcData.itemsByName[item].id, null, 1, null)[0]
        if (!recipe) {
            throw new Error(`无法制作${item}，没有找到相关配方`)
        }
        const needTalbe = recipe.requiresTable
        if (needTalbe){
            const craftingTableBlock = bot.findBlock({
                matching: mcData.blocksByName.crafting_table.id,
                maxDistance: 2
                }
            )
            if (!craftingTableBlock) {
                Bot.chat("我需要一个工作台来做这个，但我旁边没有")
                throw new Error('bot附近没有工作台，无法制作需要工作台的物品')
            }
            try{
                await Bot.craft(recipe, count, craftingTableBlock)
                Bot.chat("我用工作台做完了这个东西！")
                return { message: `bot已制作${count}个${item}，使用了工作台` }
            }
            catch(error){
                throw new Error(`制作${item}失败: ${error.message}`)
            }

        }
        else{
            try{
                await Bot.craft(recipe, count)
                Bot.chat("我做完了这个东西！")
                return { message: `bot已制作${count}个${item}，没有使用工作台` }
            }
            catch(error){
                throw new Error(`制作${item}失败: ${error.message}`)
            }
        }
    } catch (error) {
        throw new Error(`制作${item}失败: ${error.message}`)
    }
}

async function TaskCompleteCheck(bot,success, detail, nextStep) {
  // 任务完成或失败时，统一走这个出口；这里不再负责提问，只做状态收束。
  const statusText = success ? '任务完成' : '任务失败'
  const message = nextStep
    ? `${statusText}: ${detail}。下一步：${nextStep}`: `${statusText}: ${detail}`
  
  if (statusText === '任务失败') {
     await bot.chat("任务失败了，情况是：" + detail + "再次输入请求以进行重新尝试。")
     return addToHistory("system", `任务执行到此失败，情况为：${detail}`)
  }

  if (nextStep == "当前动作序列执行完毕") {
    return addToHistory("system", `当前动作序列执行完毕: ${detail}`)
  }

  return addToHistory("system", message)
}


async function ExecuteAction(Bot, Actions){
    const normalizedActions = normalizeToolName(Actions.name)
    const args = normalizeArgs(Actions.args)
    switch (normalizedActions.toLowerCase()) {
        case "move":
            return await Move(Bot, args.direction, args.blocks)
        case "jump":
            args.lastTime = args.lastTime || 5000
            return Jump(Bot, args.lastTime)
        case "turn":
            return await Turn(Bot, args.yaw, args.pitch)
        case "sneak":
            return Sneak(Bot, args.state)
        case "run":
            return Run(Bot, args.state)
        case "lookat":
            return await LookAt(Bot, args.x, args.y, args.z)
        case "moveto":
            return await MoveTo(Bot, args.x, args.y, args.z)
        case "equipiteminhand":
            return await EquipItemInHand(Bot, args.item)
        case "useiteminhand":
            return await UseItemInHand(Bot)
        case "throwitems":
            return await ThrowItems(Bot, args.item, args.count)
        case "placeblock":
            return await PlaceBlock(Bot, args.block, args.x, args.y, args.z)
        case "breakblock":
            return await BreakBlock(Bot, args.x, args.y, args.z)
        case "getposition":
            return GetPosition(Bot)
        case "getstate":
            return GetState(Bot)
        case "getinventory":
            return GetInventory(Bot)
        case "getiteminhand":
            return GetItemInHand(Bot)
        case "getaroundentities":
            return GetAroundEntities(Bot)
        case "getaroundnearesttargetblocks":
            return GetAroundNearestTargetBlocks(Bot, args.targetBlock)
        case "followplayer":
            return await FollowPlayer(Bot, args.playerName,args.state)
        case "getrecipesforitem":
            return GetRecipesForItem(Bot, args.item)
        case "craftitem":
            return CraftItem(Bot, args.item, args.count)
        case "chat":
            Bot.chat(args.message)
            addToHistory("bot", `${args.message}`)
            return { message: `已发送聊天: ${args.message}` }
        default:
            return { message: `未知的工具：${Actions.name}` }
    }
}

const QueryTools = ["GetPosition", "GetState", "GetInventory", "GetItemInHand", "GetAroundEntities", "GetAroundNearestTargetBlocks", "GetRecipesForItem"]


module.exports = {
    ExecuteAction,
    TaskCompleteCheck,
    GetBotTools,
    QueryTools,
    tools,
    SaveSkill,
}