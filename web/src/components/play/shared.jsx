import { Box, Typography } from '@mui/material'
import { useState } from 'react'
import { KeyboardArrowDown, KeyboardArrowRight } from '@mui/icons-material'
import { Button, Collapse } from '@mui/material'
import { usePanelColors, estimateTokens, buildFields, FINESSE_KEYS } from './utils'

function getValue(fullOutput, record, key) {
  const val = fullOutput[key] || record[key]
  if (val === null || val === undefined) return ''
  if (typeof val === 'string') return val
  if (typeof val === 'object') return JSON.stringify(val, null, 2)
  return String(val)
}

// 通用字段卡列表（所有引擎共用）；excludeKeys 可选排除（如飞牌字段已单独印章展示）
export function RawFields({ fullOutput, record, excludeKeys = [] }) {
  const { bgCode, borderCode } = usePanelColors()
  const fields = buildFields(fullOutput).filter(f => !excludeKeys.includes(f.key))
  return (
    <>
      {fields.map(({ key, label, color, multiline }) => {
        const value = getValue(fullOutput, record, key)
        if (!value) return null
        return (
          <Box key={key} sx={{ mt: 0.5 }}>
            {multiline ? (
              <Box>
                <Typography variant="body2" sx={{ fontSize: '0.7rem', color, fontWeight: 500 }}>
                  {label}:
                </Typography>
                <Box component="pre" sx={{
                  mt: 0.25, p: 0.5, background: bgCode, borderRadius: 1,
                  fontSize: '0.75rem', lineHeight: 1.3,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  border: borderCode, maxHeight: '120px', overflow: 'auto',
                  color,
                }}>
                  {value}
                </Box>
              </Box>
            ) : (
              <Typography variant="body2" sx={{ fontSize: '0.7rem', color }}>
                <strong>{label}:</strong> {value}
              </Typography>
            )}
          </Box>
        )
      })}
    </>
  )
}

// 约束与已出牌对照表（所有引擎共用）
export function SuitCountsTable({ fullOutput }) {
  const { isDark, borderCode, colorMuted } = usePanelColors()
  const initTxt = fullOutput['叫牌约束']
  const latestTxt = fullOutput['最新约束']
  const playedStats = fullOutput['各家已出统计']
  if (!initTxt && !latestTxt && !playedStats) return null
  const parseRows = (text) => {
    const map = {}
    for (const line of String(text || '').split('\n')) {
      const m = line.match(/^([东西南北]):\s*(.*)$/)
      if (m) map[m[1]] = m[2]
    }
    return map
  }
  const initRows = parseRows(initTxt)
  const latestRows = parseRows(latestTxt)
  const positions = ['南', '西', '北', '东']
  const noInit = !initTxt || initTxt.includes('无约束')
  const noLatest = !latestTxt || latestTxt.includes('无约束') || latestTxt.includes('全部满足')
  const tdSx = { border: borderCode, p: 0.5, fontSize: '0.65rem', lineHeight: 1.3, verticalAlign: 'top' }
  const thSx = { ...tdSx, fontWeight: 600, background: isDark ? 'rgba(255,255,255,0.06)' : '#f5f5f5', color: 'text.primary' }
  return (
    <Box key="constraint-table" sx={{ mt: 0.5 }}>
      <Typography variant="caption" sx={{ fontSize: '0.7rem', color: '#1976d2', fontWeight: 600, display: 'block', mb: 0.3 }}>
        约束与已出牌对照
      </Typography>
      <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
        <Box component="thead">
          <Box component="tr">
            <Box component="th" sx={{ ...thSx, whiteSpace: 'nowrap' }}>位置</Box>
            <Box component="th" sx={thSx}>初始约束</Box>
            <Box component="th" sx={thSx}>最新约束</Box>
            <Box component="th" sx={{ ...thSx, whiteSpace: 'nowrap' }}>已出点力</Box>
            {['♠', '♥', '♦', '♣'].map(s => (
              <Box component="th" key={s} sx={{ ...thSx, textAlign: 'center' }}>{s}</Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {positions.map(pos => {
            const st = playedStats && playedStats[pos]
            return (
              <Box component="tr" key={pos}>
                <Box component="td" sx={{ ...tdSx, fontWeight: 600 }}>{pos}</Box>
                <Box component="td" sx={{ ...tdSx, color: colorMuted }}>{initRows[pos] || '—'}</Box>
                <Box component="td" sx={{ ...tdSx, color: colorMuted }}>{latestRows[pos] || '—'}</Box>
                <Box component="td" sx={{ ...tdSx, textAlign: 'center' }}>{st ? st.hcp : '—'}</Box>
                {['♠', '♥', '♦', '♣'].map(s => (
                  <Box component="td" key={s} sx={{ ...tdSx, textAlign: 'center' }}>{st ? (st[s] ?? '—') : '—'}</Box>
                ))}
              </Box>
            )
          })}
        </Box>
      </Box>
      {(noInit || noLatest) && (
        <Typography variant="caption" sx={{ color: colorMuted, display: 'block', mt: 0.2 }}>
          {noInit ? '计入此项时初始无约束（随机采样），不参与推断。' : ''}
          {noLatest ? '最新约束为剩余部分约束（已随出牌扣减）。' : ''}
        </Typography>
      )}
    </Box>
  )
}

// 输入模式：显示传给AI的完整提示词（所有引擎共用，LLM 打牌旧纪录兼容 llm_review）
export function PromptView({ fullOutput, record, prompt }) {
  const { bgCode, colorMuted } = usePanelColors()
  const reviewRaw = fullOutput.llm_review
  const review = reviewRaw && typeof reviewRaw === 'string' ? JSON.parse(reviewRaw) : reviewRaw
  const llmPrompt = review ? review.llm_prompt : null
  const displayPrompt = llmPrompt || record.prompt || prompt
  return displayPrompt ? (
    <Box>
      <Typography variant="caption" sx={{ display: 'block', color: colorMuted, fontSize: '0.7rem', mb: 0.25 }}>
        提示词长度: {displayPrompt.length.toLocaleString()} 字符
        &nbsp;·&nbsp;约 {(estimateTokens(displayPrompt)).toLocaleString()} token
      </Typography>
      <Box component="pre" sx={{
        p: 0.75, background: bgCode, borderRadius: 1,
        fontSize: '0.7rem', lineHeight: 1.4,
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        border: '1px solid #e9ecef', maxHeight: '400px', overflow: 'auto',
      }}>
        {displayPrompt}
      </Box>
    </Box>
  ) : (
    <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
      无输入数据
    </Typography>
  )
}

// 飞牌/续飞相关信息的"印章"区块：带色边框小卡，展示在核心逻辑之前更醒目
export function FinesseStamps({ fullOutput }) {
  const { isDark, colorMuted } = usePanelColors()
  const items = Object.keys(fullOutput || {})
    .filter(k => FINESSE_KEYS.includes(k) && fullOutput[k] != null && fullOutput[k] !== '')
  if (!items.length) return null

  // 印章配色：启动类橙色、续飞/接应类紫色、原则类绿色
  const stampColors = {
    '窗口期启动': '#e65100', '继续飞牌': '#e65100', '飞牌续': '#e65100', '9砸回手': '#e65100',
    '飞牌接应': '#7b1fa2', '领出飞牌': '#7b1fa2', '飞牌迁移': '#6a1b9a', '八九原则': '#2e7d32',
  }

  const fmt = (label, val) => {
    if (val == null || val === '') return ''
    if (typeof val === 'string') return val
    if (typeof val === 'object') {
      // 从飞牌描述对象提取关键字段拼成一行
      const parts = []
      if (val['花色']) parts.push(`花色${val['花色']}`)
      if (val['对象'] && typeof val['对象'] !== 'boolean') {
        const rankName = { 14: 'A', 13: 'K', 12: 'Q', 11: 'J', 10: 'T' }[val['对象']]
        parts.push(`对象${rankName || val['对象']}`)
      }
      if (val['Δ'] != null && val['Δ'] !== '') parts.push(`Δ${val['Δ']}`)
      if (val['改选']) parts.push(`改出${val['改选']}`)
      if (val['原选']) parts.push(`原选${val['原选']}`)
      if (val['领出']) parts.push(`领出${val['领出']}`)
      if (val['说明'] && val['说明'] !== 'true' && val['说明'] !== 'false') parts.push(val['说明'])
      return parts.join(' · ') || JSON.stringify(val)
    }
    return String(val)
  }

  return (
    <Box sx={{ mt: 0.5, display: 'flex', flexDirection: 'column', gap: 0.4 }}>
      {items.map(k => (
        <Box key={k} sx={{
          p: 0.5, borderRadius: 0.5,
          bgcolor: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa',
          borderLeft: `3px solid ${stampColors[k] || '#1976d2'}`,
          border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#eee'}`,
        }}>
          <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, lineHeight: 1.3, display: 'block' }}>
            <Box component="span" sx={{ fontWeight: 600, color: stampColors[k] || '#1976d2' }}>{k}</Box>
            {` · ${fmt(k, fullOutput[k])}`}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

// 探针结果：本侧 finesse_probe + 伙伴侧 伙伴探针（{花色: {对象, Δ, 引牌, 全}}）。
// 与飞牌印章同一控件样式、单行显示；"全" 列出同花色全部对象探针（K/Q/...各一条）
export function FinesseProbeView({ fullOutput }) {
  const { isDark, colorMuted } = usePanelColors()
  const rankName = { 14: 'A', 13: 'K', 12: 'Q', 11: 'J', 10: 'T' }
  const confirmMap = (fullOutput && fullOutput._probe_confirm) || {}
  const sources = [
    { key: 'finesse_probe', label: '探针' },
    { key: '伙伴探针', label: '伙伴探针' },
  ]
  const rows = []
  for (const { key, label } of sources) {
    const probe = fullOutput && fullOutput[key]
    if (!probe || typeof probe !== 'object') continue
    for (const s of Object.keys(probe)) {
      const info = probe[s]
      if (!info || typeof info !== 'object') continue
      const all = Array.isArray(info.全) && info.全.length ? info.全 : [info]
      for (const e of all) {
        rows.push({ label, s, obj: e.对象, delta: e.Δ, lead: e.引牌 })
      }
    }
  }
  // 同侧+同花色+同一飞牌对象 → 只显示 Δ 更高者；不同侧不合并
  const merged = []
  const seen = new Map()
  for (const r of rows) {
    const k = `${r.label}|${r.s}|${r.obj}`
    const prev = seen.get(k)
    if (!prev || (r.delta ?? -1) > (prev.delta ?? -1)) {
      seen.set(k, { ...r, orig: prev })
    }
  }
  for (const r of seen.values()) {
    merged.push(r)
  }
  if (!merged.length) return null
  return (
    <Box sx={{ mt: 0.5, display: 'flex', flexDirection: 'column', gap: 0.4 }}>
      {merged.map((r, i) => {
        const key = `${r.label}|${r.s}|${r.lead}`
        const confirmed = key in confirmMap ? !!confirmMap[key] : null
        return (
          <Box key={i} sx={{
            p: 0.5, borderRadius: 0.5,
            bgcolor: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa',
            borderLeft: '3px solid #1976d2',
            border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#eee'}`,
          }}>
            <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, lineHeight: 1.3, display: 'block' }}>
              <Box component="span" sx={{ fontWeight: 600, color: '#1976d2' }}>{r.label}</Box>
              {` · 花色${r.s} · 对象${rankName[r.obj] || r.obj} · Δ${r.delta} · 引牌${r.lead}`}
              {confirmed === true && (
                <Box component="span" sx={{ fontWeight: 700, color: '#2e7d32' }}> · ✓飞结构</Box>
              )}
              {confirmed === false && (
                <Box component="span" sx={{ color: '#c62828' }}> · ✗未确认</Box>
              )}
            </Typography>
          </Box>
        )
      })}
    </Box>
  )
}

// 可折叠区块（用于"候选对比"等低频查看内容，默认收起）
export function CollapseSection({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Box sx={{ mt: 0.5 }}>
      <Button
        size="small"
        onClick={() => setOpen(o => !o)}
        sx={{ fontSize: '0.65rem', textTransform: 'none', p: 0, minWidth: 0, color: '#1976d2' }}
      >
        {open ? <KeyboardArrowDown sx={{ fontSize: 14 }} /> : <KeyboardArrowRight sx={{ fontSize: 14 }} />}
        {title}
      </Button>
      <Collapse in={open}>
        <Box sx={{ p: 0.5 }}>
          {children}
        </Box>
      </Collapse>
    </Box>
  )
}