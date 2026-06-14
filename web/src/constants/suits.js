// 共享的花色常量，避免在多个组件中重复定义

export const SUIT_SYMBOLS = {
  spades: '♠',
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
}

// 统一花色颜色（唯一数据源）
// 亮色模式
const LIGHT_SUIT_COLORS = {
  '♠': '#1e293b',
  '♥': '#dc2626',
  '♦': '#ea580c',
  '♣': '#1e293b',
}

// 暗色模式（在深色背景上需要更亮才能看清）
const DARK_SUIT_COLORS = {
  '♠': '#cbd5e1',
  '♥': '#f87171',
  '♦': '#fb923c',
  '♣': '#cbd5e1',
}

export const SUIT_COLORS = {
  spades: LIGHT_SUIT_COLORS['♠'],
  hearts: LIGHT_SUIT_COLORS['♥'],
  diamonds: LIGHT_SUIT_COLORS['♦'],
  clubs: LIGHT_SUIT_COLORS['♣'],
}

// 直接用花色符号作为 key 的颜色映射（亮色模式）
export const SUIT_COLOR_MAP = { ...LIGHT_SUIT_COLORS }

// 从花色符号获取颜色，支持暗色模式
export function getSuitColor(suitSymbol, isDark = false) {
  if (isDark) {
    return DARK_SUIT_COLORS[suitSymbol] || '#cbd5e1'
  }
  return LIGHT_SUIT_COLORS[suitSymbol] || '#1e293b'
}
