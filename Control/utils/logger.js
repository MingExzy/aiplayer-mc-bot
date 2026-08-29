/**
 * 轻量结构化日志（Node 端）
 * 输出 JSON 行，自动带 ts / level / event，业务字段通过 data 传入（如 trace_id）。
 * 不做轮转、不做装饰器，保持最小。
 */

function log(level, event, data = {}) {
  const entry = { ts: new Date().toISOString(), level, event, ...data }
  const line = JSON.stringify(entry)
  if (level === 'error') {
    console.error(line)
  } else {
    console.log(line)
  }
}

module.exports = {
  info: (event, data) => log('info', event, data),
  warn: (event, data) => log('warn', event, data),
  error: (event, data) => log('error', event, data),
}
