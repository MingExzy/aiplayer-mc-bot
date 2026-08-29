/**
 * 工具注册中心（支持运行时动态注册）
 *
 * 职责：
 *   - 启动时扫描 tools/ 目录，加载所有「工具定义」文件（.js）
 *   - 监听 tools/ 目录：新增 / 修改 / 删除文件时自动注册、更新、移除（无需重启）
 *   - 工具定义格式：{ name, args, class, description, execute(bot, args) }
 *   - 每次变更后自动同步 node/tools.json，Python 端按 mtime 热重载即可感知
 *
 * 加新工具三种方式：
 *   1. 直接往 tools/ 目录放一个符合格式的 .js 文件（目录监听自动生效）
 *   2. 运行中调用 register(toolDef) / registerFromFile(filePath)
 *   3. 通过快捷指令 !注册工具 <JSON>（见 commands/quick.js）
 */

const path = require('path')
const fs = require('fs')

class ToolRegistry {
  constructor(toolsJsonPath = '') {
    this._tools = new Map()          // 工具名 -> 工具定义
    this._toolsJsonPath = toolsJsonPath
    this._fileToolNames = new Map()  // 工具文件绝对路径 -> 工具名（删除文件时反查）
    this._loaded = false
    this._watcher = null
    this._watchTimer = null
  }

  /** 扫描目录，加载所有 .js 工具文件（进程内只执行一次） */
  loadAll(dir) {
    if (this._loaded) return
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.js'))
    for (const file of files) {
      this.registerFromFile(path.join(dir, file))
    }
    this._loaded = true
    console.log(`[registry] 共 ${this._tools.size} 个工具`)
  }

  /** 运行时注册（或覆盖）一个工具定义 */
  register(toolDef, source = '') {
    if (!toolDef || typeof toolDef.name !== 'string' || !toolDef.name.trim()) {
      console.warn(`[registry] 跳过 ${source || '未知来源'}: 缺少 name`)
      return false
    }
    if (typeof toolDef.execute !== 'function') {
      console.warn(`[registry] 跳过 ${toolDef.name}: 缺少 execute 函数`)
      return false
    }
    const existed = this._tools.has(toolDef.name)
    this._tools.set(toolDef.name, toolDef)
    console.log(`[registry] ${existed ? '更新' : '已加载'}: ${toolDef.name}`)
    return true
  }

  /** 从文件加载并注册（清 require 缓存，支持同文件热更新） */
  registerFromFile(filePath) {
    const abs = path.resolve(filePath)
    if (!fs.existsSync(abs)) return false
    delete require.cache[require.resolve(abs)]

    let toolDef
    try {
      toolDef = require(abs)
    } catch (err) {
      console.error(`[registry] 加载 ${abs} 失败: ${err.message}`)
      return false
    }

    if (this.register(toolDef, abs)) {
      this._fileToolNames.set(abs, toolDef.name)
      return toolDef
    }
    return false
  }

  /** 按文件移除工具（清缓存并注销） */
  unregisterFile(filePath) {
    const abs = path.resolve(filePath)
    const name = this._fileToolNames.get(abs)
    if (name) {
      this.unregister(name)
      this._fileToolNames.delete(abs)
    }
    try {
      delete require.cache[require.resolve(abs)]
    } catch (_) { /* 文件已删除时无需清理 */ }
    return !!name
  }

  /** 移除已注册的工具 */
  unregister(name) {
    if (!this._tools.delete(name)) return false
    console.log(`[registry] 已移除: ${name}`)
    return true
  }

  /** 大小写不敏感查找工具定义 */
  _find(name) {
    if (!name) return undefined
    if (this._tools.has(name)) return this._tools.get(name)
    const lower = String(name).toLowerCase()
    for (const [key, tool] of this._tools) {
      if (key.toLowerCase() === lower) return tool
    }
    return undefined
  }

  /** 是否已注册（大小写不敏感） */
  has(name) {
    return !!this._find(name)
  }

  /** 执行指定工具（大小写不敏感） */
  async execute(bot, name, args) {
    const tool = this._find(name)
    if (!tool) throw new Error(`未知工具: ${name}`)
    return await tool.execute(bot, args || {})
  }

  /** 返回注册表全部工具（供展示 / 同步 tools.json） */
  getList() {
    const list = []
    for (const t of this._tools.values()) {
      list.push({ name: t.name, args: t.args, class: t.class || 'Tool', description: t.description })
    }
    return list
  }

  /**
   * 把注册表全量同步进 tools.json（注册表就是唯一的工具源）：
   *   启动时生成 21 个原子工具；运行时注册/更新/删除后再次生成。
   * Python 端监听该文件 mtime 热重载，因此无需重启 Python 服务。
   */
  syncToolsJson(toolsJsonPath = this._toolsJsonPath) {
    this._toolsJsonPath = toolsJsonPath
    const list = []
    for (const t of this._tools.values()) {
      list.push({ name: t.name, args: t.args, class: t.class || 'Tool', description: t.description })
    }
    fs.writeFileSync(toolsJsonPath, JSON.stringify(list, null, 2) + '\n', 'utf-8')
    console.log(`[registry] tools.json 已同步: ${list.length} 个工具`)
    return list
  }

  /**
   * 监听 tools/ 目录：新增 / 修改 / 删除工具文件时自动注册、更新、移除。
   * 编辑保存会触发多次事件，用 300ms 防抖合并处理。
   */
  watch(dir) {
    if (this._watcher) return
    const absDir = path.resolve(dir)
    const pending = new Set()

    const flush = () => {
      this._watchTimer = null
      for (const fileName of pending) this._handleFileEvent(absDir, fileName)
      pending.clear()
    }

    this._watcher = fs.watch(absDir, (_eventType, fileName) => {
      if (!fileName || !fileName.endsWith('.js')) return
      pending.add(fileName)
      if (this._watchTimer) clearTimeout(this._watchTimer)
      this._watchTimer = setTimeout(flush, 300)
    })
    this._watcher.on('error', err => console.error(`[registry] 目录监听错误: ${err.message}`))
    console.log(`[registry] 正在监听: ${absDir}`)
  }

  /** 处理单个文件事件：存在→加载/更新，不存在→移除 */
  _handleFileEvent(dir, fileName) {
    const filePath = path.join(dir, fileName)
    if (!fs.existsSync(filePath)) {
      if (this.unregisterFile(filePath)) this.syncToolsJson()
      return
    }
    if (this.registerFromFile(filePath)) {
      this.syncToolsJson()
    }
  }

  /**
   * 从外部输入（JSON 定义）生成工具文件并写入 tools/ 目录。
   * 定义格式：{ name, args, class, description, code }
   *   code 为 execute(bot, args) 的函数体源码字符串（可用 bot、args 两个变量）。
   */
  createToolFile(def, dir) {
    const name = def && def.name
    if (!name || !/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) {
      throw new Error(`工具名不合法（须为英文字母开头的标识符）: ${name}`)
    }
    const code = def.code
    if (typeof code !== 'string' || !code.trim()) {
      throw new Error('工具缺少 code（execute 函数体源码）')
    }
    try {
      new Function('bot', 'args', code) // 语法预检
    } catch (err) {
      throw new Error(`code 语法错误: ${err.message}`)
    }

    const args = Array.isArray(def.args) ? def.args : []
    const lines = [
      '// 自动生成工具: ' + name,
      'module.exports = {',
      '  name: ' + JSON.stringify(name) + ',',
      '  args: ' + JSON.stringify(args) + ',',
      '  class: ' + JSON.stringify(def.class || 'DynamicTool') + ',',
      '  description: ' + JSON.stringify(def.description || '') + ',',
      '  async execute(bot, args) {',
      ...code.split('\n').map(line => '    ' + line),
      '  }',
      '}',
      ''
    ]
    const filePath = path.join(dir, `${name}.js`)
    fs.writeFileSync(filePath, lines.join('\n'), 'utf-8')
    console.log(`[registry] 工具文件已生成: ${filePath}`)
    return filePath
  }
}

const TOOLS_DIR = path.join(__dirname, '..', 'tools')
const instance = new ToolRegistry(path.join(__dirname, '..', 'tools.json'))
// 首次 require 时扫描 tools/ 目录，同步 tools.json，并开始监听目录变化
instance.loadAll(TOOLS_DIR)
instance.syncToolsJson()
instance.watch(TOOLS_DIR)
module.exports = instance
