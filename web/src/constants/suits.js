// 共享的花色常量，避免在多个组件中重复定义

export const SUIT_SYMBOLS = {
  spades: '♠',
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
}

export const SUIT_COLORS = {
  spades: '#000',
  hearts: '#e53935',
  diamonds: '#e53935',
  clubs: '#000',
}

// 直接用花色符号作为 key 的颜色映射
export const SUIT_COLOR_MAP = {
  '♠': '#000',
  '♥': '#e53935',
  '♦': '#e53935',
  '♣': '#000',
}

// 从花色符号获取颜色
export function getSuitColor(suitSymbol) {
  return SUIT_COLOR_MAP[suitSymbol] || '#000'
}
