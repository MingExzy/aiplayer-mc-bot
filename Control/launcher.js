/**
 * 统一入口 — 多 Bot 启动器 / 单个 Bot 进程
 * （合并原 launcher.js + main.js，不再有独立的单 Bot 入口）
 *
 * 用法：
 *   node launcher.js           ← 交互式输入启动几个 Bot
 *   node launcher.js 3         ← 启动 3 个 Bot
 *   node launcher.js 1         ← 启动 1 个 Bot（等效旧的单 Bot 启动）
 *   node launcher.js --bot     ← 内部子进程模式：以 BOT_ID 身份运行单个 Bot
 */

const { spawn } = require('child_process')
const readline = require('readline')
const { initBot, setBotId } = require('./bot')
const { processCommand } = require('./commands/quick')

// ═══════════════════════════════════════════════
// 子进程模式：充当一个 Bot（原 main.js 逻辑）
// ═══════════════════════════════════════════════
function runSingleBot() {
  const botId = process.env.BOT_ID || '1'
  console.log(`Bot #${botId} 启动中...`)
  setBotId(botId)

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  })

  const Bot = initBot(`AIPlayer${botId}`)
  console.log('Bot 启动...')

  rl.on('line', (input) => {
    if (!input.startsWith('!') || !Bot) return
    // 过滤 @botX 前缀
    const botTag = `@bot${botId}`
    if (input.startsWith('@')) {
      const tag = input.split(/\s+/)[0]
      if (tag !== botTag) return
      input = input.slice(tag.length).trim()
    } else if (botId !== '1') {
      return
    }
    processCommand(Bot, input)
  })
}

// ═══════════════════════════════════════════════
// 父进程模式：多 Bot 启动器（原 launcher.js 逻辑）
// ═══════════════════════════════════════════════
function askCount() {
  return new Promise(resolve => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    })
    rl.question('启动几个 Bot？', answer => {
      const n = parseInt(answer, 10)
      rl.close()
      resolve(isNaN(n) ? 0 : n)
    })
  })
}

async function launchBots() {
  const argCount = parseInt(process.argv[2], 10)
  const n = argCount || await askCount()

  if (n < 1) {
    console.log('数量无效，退出。')
    process.exit(0)
  }

  console.log(`\n启动 ${n} 个 Bot...\n`)

  const children = []
  const API_BASE = process.env.FASTAPI_URL || config.fastapi_url

  for (let i = 1; i <= n; i++) {
    const child = spawn('node', ['launcher.js', '--bot'], {
      cwd: __dirname,
      stdio: ['inherit', 'pipe', 'pipe'],
      env: { ...process.env, BOT_ID: String(i) }
    })

    fetch(`${API_BASE}/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_id: i, pid: child.pid })
    }).catch(() => {})

    child.on('exit', () => {
      fetch(`${API_BASE}/unregister`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_id: i })
      }).catch(() => {})
    })

    child.stdout.on('data', data => {
      const lines = data.toString().trim()
      for (const line of lines.split('\n')) {
        console.log(`[Bot${i}] ${line}`)
      }
    })

    child.stderr.on('data', data => {
      console.error(`[Bot${i} ERR] ${data.toString().trim()}`)
    })

    child.on('exit', code => {
      console.log(`[Bot${i}] 退出 (代码: ${code})`)
    })

    children.push(child)
  }

  // 拦截快捷键命令并分发
  process.stdin.on('data', data => {
    const line = data.toString().trim()
    if (!line.startsWith('!')) return

    const atIdx = line.indexOf(' @')
    if (atIdx > 0) {
      // 指定 Bot: "挖矿 @bot2"
      const botId = line.slice(atIdx + 1).replace('bot', '')
      const idx = parseInt(botId, 10) - 1
      if (idx >= 0 && idx < children.length) {
        children[idx].stdin.write(line.slice(0, atIdx) + '\n')
      }
    } else {
      // 全部分发
      for (const child of children) {
        child.stdin.write(line + '\n')
      }
    }
  })

  console.log(`已启动 ${n} 个 Bot，进程 ID: ${children.map(c => c.pid).join(', ')}`)
  console.log('按 Ctrl+C 关闭所有 Bot\n')
  console.log('输入 !坐标 等快捷命令 → 全部分发')
  console.log('输入 "挖矿 @bot2" → 只发 Bot2')

  // 优雅关闭
  const shutdown = () => {
    console.log('\n正在关闭所有 Bot...')
    for (const child of children) {
      child.kill('SIGTERM')
    }
    process.exit(0)
  }
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}

// ═══════════════════════════════════════════════
// 入口分发
// ═══════════════════════════════════════════════
if (process.argv.includes('--bot')) {
  runSingleBot()
} else {
  launchBots()
}
