// 通用格式化工具（v1.61）

/** 总耗时格式化：秒 → "X分Y秒" / "Y秒" / "X分"（小于1秒显示"0秒"） */
export const formatTotalTime = (seconds) => {
  if (seconds == null || isNaN(seconds)) return ''
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  return r > 0 ? `${m}分${r}秒` : `${m}分`
}
