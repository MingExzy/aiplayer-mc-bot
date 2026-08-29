/**
 * 规划响应解析工具
 * （原 user_utils.js）
 *
 * 职责：把 Python/LLM 返回的各种形态的规划响应统一解析为动作列表。
 * 已移除无使用方的 extractJsonFromSSE（旧 SSE 时代遗留）。
 */


function parseJsonCandidate(text) {
  const fencedMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const source = fencedMatch ? fencedMatch[1] : text

  try {
    return JSON.parse(source)
  } catch (_) {
    const firstBrace = source.indexOf('{')
    const firstBracket = source.indexOf('[')
    const startIndex = [firstBrace, firstBracket].filter(index => index >= 0).sort((a, b) => a - b)[0]

    if (startIndex === undefined) {
      throw new Error('规划响应不包含可解析的 JSON')
    }

    const endIndex = Math.max(source.lastIndexOf('}'), source.lastIndexOf(']'))
    if (endIndex <= startIndex) {
      throw new Error('规划响应 JSON 边界不完整')
    }

    return JSON.parse(source.slice(startIndex, endIndex + 1))
  }
}

function normalizeActionList(plan) {
  if (!plan) {
    return []
  }

  if (Array.isArray(plan)) {
    return plan
  }

  if (Array.isArray(plan.actions)) {
    return plan.actions
  }

  if (Array.isArray(plan.tool_calls)) {
    return plan.tool_calls.map(toolCall => ({
      name: toolCall.name || toolCall.function?.name,
      args: toolCall.args || toolCall.arguments || toolCall.function?.arguments || {}
    }))
  }

  if (typeof plan.content === 'string') {
    return normalizeActionList(parseJsonCandidate(plan.content))
  }

  if (typeof plan.reply === 'string') {
    return normalizeActionList(parseJsonCandidate(plan.reply))
  }

  return []
}

module.exports = {
  parseJsonCandidate,
  normalizeActionList
}
