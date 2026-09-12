import { useTheme } from '@mui/material'

// 面板配色（与 PlayDetailPanel 原定义一致）
export function usePanelColors() {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  return {
    isDark,
    bgWhite: isDark ? 'rgba(30, 41, 59, 0.7)' : 'white',
    bgCode: isDark ? 'rgba(255,255,255,0.05)' : '#f8f9fa',
    borderCode: isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid #e9ecef',
    colorMuted: isDark ? '#94a3b8' : '#888',
  }
}

// 估算token数（中文字符≈1 token，其他≈4字符/token）
export function estimateTokens(text) {
  if (!text) return 0
  let chinese = 0
  let other = 0
  for (const ch of text) {
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) chinese++
    else other++
  }
  return Math.ceil(chinese + other / 4)
}

export const FIELD_COLORS = ['#e65100', 'text.primary', '#2e7d32', '#1976d2', '#37474f', '#1565c0']
export const SKIP_KEYS = ['mcts_stats', 'tiered_phase', 'tiered_dd_fallback', 'validation_warning', 'llm_review', 'engine_phase', 'llm_review_status', '叫牌约束', '最新约束', '各家已出统计', 'finesse_probe', '伙伴探针', '_probe_suits', '_probe_confirm', '推荐出牌']

// 飞牌与续飞相关字段：DD 视图提升到核心逻辑前用印章区块展示
export const FINESSE_KEYS = ['窗口期启动', '继续飞牌', '飞牌续', '9砸回手', '飞牌接应', '八九原则', '领出飞牌', '飞牌迁移']

// 从 fullOutput 提取可展示字段（排除内部键，dd_hint 置顶）
export function buildFields(fullOutput) {
  const fields = Object.keys(fullOutput || {})
    .filter(k => !SKIP_KEYS.includes(k) && fullOutput[k] != null && fullOutput[k] !== '')
    .map((k, i) => ({
      key: k,
      label: k,
      color: FIELD_COLORS[i % FIELD_COLORS.length],
      multiline: typeof fullOutput[k] === 'string' && fullOutput[k].length > 40,
    }))
  if (fullOutput.dd_hint && !fields.find(f => f.key === 'dd_hint')) {
    fields.unshift({ key: 'dd_hint', label: 'DD注入', color: '#e65100', multiline: true })
  }
  return fields
}