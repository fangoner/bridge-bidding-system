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
  '♦': '#dc2626',
  '♣': '#1e293b',
}

// 暗色模式（深色背景用，浅色文字）
const DARK_SUIT_COLORS = {
  '♠': '#e2e8f0',
  '♥': '#f87171',
  '♦': '#f87171',
  '♣': '#e2e8f0',
}

// 暗色模式下的卡片牌面用色（白底卡片，需深色文字）
const DARK_CARD_SUIT_COLORS = {
  '♠': '#1e293b',
  '♥': '#dc2626',
  '♦': '#dc2626',
  '♣': '#1e293b',
}

export const SUIT_COLORS = {
  spades: LIGHT_SUIT_COLORS['♠'],
  hearts: LIGHT_SUIT_COLORS['♥'],
  diamonds: LIGHT_SUIT_COLORS['♦'],
  clubs: LIGHT_SUIT_COLORS['♣'],
}

// 直接用花色符号作为 key 的颜色映射（亮色模式）
export const SUIT_COLOR_MAP = { ...LIGHT_SUIT_COLORS }

// 从花色符号获取颜色，支持暗色模式（深色背景用）
export function getSuitColor(suitSymbol, isDark = false) {
  if (isDark) {
    return DARK_SUIT_COLORS[suitSymbol] || '#cbd5e1'
  }
  return LIGHT_SUIT_COLORS[suitSymbol] || '#1e293b'
}

// 卡片牌面用色（白底卡片，无论亮暗模式都用深色保证对比度）
export function getCardSuitColor(suitSymbol) {
  return DARK_CARD_SUIT_COLORS[suitSymbol] || LIGHT_SUIT_COLORS[suitSymbol] || '#1e293b'
}
