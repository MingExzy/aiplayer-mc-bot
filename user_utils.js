

function extractJsonFromSSE(sseText) {
  const lines = sseText.split('\n');
  for (const line of lines) {
    if (line.startsWith('data:')) {
      const jsonStr = line.substring(5).trim(); // 去掉 'data:' 前缀
      return JSON.parse(jsonStr);
    }
  }
  throw new Error('SSE 响应中未找到 data 字段');
}


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
      throw new Error('MCP 回复不包含可解析的 JSON')
    }

    const endIndex = Math.max(source.lastIndexOf('}'), source.lastIndexOf(']'))
    if (endIndex <= startIndex) {
      throw new Error('MCP 回复 JSON 边界不完整')
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
  extractJsonFromSSE,
  parseJsonCandidate,
  normalizeActionList
}