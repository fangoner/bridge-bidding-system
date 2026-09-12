import { Box, Typography, ToggleButton, ToggleButtonGroup } from '@mui/material'
import { useEffect, useState } from 'react'
import { usePanelColors } from './utils'

// 单个候选条
function BarRow({ candidate, barVal, maxVal, color, showDdMode, ddScoringMode, isAlphaMu, inherited, ddTricks, ddImp, ddRate, ddMn, ddMx, vmin, vmax }) {
  const { isDark, colorMuted } = usePanelColors()
  // IMP 模式：0 点不固定，随数据范围动态定位（负值少时 0 点靠左，避免左侧大片空白）
  const isImp = showDdMode && ddScoringMode === 'imp'
  const trackBg = isDark ? 'rgba(255,255,255,0.06)' : '#eee'
  const span = (vmax - vmin) || 1
  const pct = (v) => ((v - vmin) / span) * 100
  const zP = pct(0)
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.15 }}>
      <Typography variant="caption" sx={{ width: 28, flexShrink: 0, fontSize: '0.7rem', fontWeight: 600, color: isDark ? '#e0e0e0' : '#333' }}>
        {candidate.card}
      </Typography>
      <Box sx={{ width: 360, flexShrink: 0, position: 'relative', height: 12, borderRadius: 0.5, overflow: 'hidden' }}>
        {isImp ? (
          <>
            <Box sx={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${zP}%`, bgcolor: trackBg }} />
            <Box sx={{ position: 'absolute', left: `${zP}%`, top: 0, bottom: 0, right: 0, bgcolor: trackBg }} />
            <Box sx={{ position: 'absolute', left: `${zP}%`, top: 0, bottom: 0, width: 1, bgcolor: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.35)' }} />
            <Box sx={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${pct(Math.min(barVal, 0))}%`,
              width: `${Math.abs(barVal) / span * 100}%`,
              bgcolor: barVal < 0 ? '#e53935' : color,
              opacity: inherited ? 0.45 : 1,
              borderRadius: 0.5,
              transition: 'width 0.3s, opacity 0.3s',
            }} />
          </>
        ) : (
          <>
            <Box sx={{ position: 'absolute', inset: 0, bgcolor: trackBg, borderRadius: 0.5 }} />
            <Box sx={{
              position: 'absolute', left: 0, top: 0, bottom: 0,
              width: `${Math.min(Math.abs(barVal) / maxVal, 1) * 100}%`,
              bgcolor: color,
              opacity: inherited ? 0.45 : 1,
              borderRadius: 0.5,
              transition: 'width 0.3s, opacity 0.3s',
            }} />
          </>
        )}
      </Box>
      <Typography variant="caption" sx={{ flex: 1, minWidth: 0, fontSize: '0.65rem', color: colorMuted, textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {isAlphaMu
          ? `${((candidate.success_rate || 0) * 100).toFixed(0)}% · ${candidate.avg_tricks ?? '?'}墩 · ${candidate.success_count || 0}/${candidate.total_useful || '?'} · front${candidate.front_size || 1}${inherited ? ' · 继承' : ''}`
          : showDdMode
            ? (
              <Box component="span" sx={{ whiteSpace: 'nowrap' }}>
                <Box component="span" sx={{ fontWeight: ddScoringMode === 'avg_tricks' ? 700 : 400 }}>
                  {ddTricks != null ? `${ddTricks}墩` : '?'}{ddMn != null && ddMx != null ? `[${ddMn}-${ddMx}]` : ''}
                </Box>
                {' · '}
                <Box component="span" sx={{ fontWeight: ddScoringMode === 'imp' ? 700 : 400 }}>{ddImp != null ? `${ddImp >= 0 ? '+' : ''}${ddImp}IMP` : '?'}</Box>
                {' · '}
                <Box component="span" sx={{ fontWeight: ddScoringMode === 'make_rate' ? 700 : 400 }}>{ddRate != null ? `${(ddRate * 100).toFixed(1)}%` : '?'}</Box>
              </Box>
            )
            : `${candidate.avg_tricks}墩`}
      </Typography>
    </Box>
  )
}

// αμ 候选对比条：bar = success_rate（成功率 0-1）
export function AlphaMuBars({ mctsData }) {
  const { colorMuted } = usePanelColors()
  const candidates = mctsData.candidates || []
  if (!candidates.length) return null
  const barValues = candidates.map(c => (c.success_rate || 0) * 100)
  const maxVal = Math.max(...barValues.map(v => Math.abs(v)), 0.01)
  const barColors = ['#263238', '#37474f', '#546e7a', '#78909c', '#b0bec5']
  return (
    <Box sx={{ mt: 0.5 }}>
      <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, mb: 0.25, display: 'block' }}>
        αμ: {mctsData.num_worlds || '?'} worlds{mctsData.worlds_source ? `(${mctsData.worlds_source === 'enumerated' ? '枚举' : '采样'})` : ''} · depth≤{mctsData.M ?? 4} · {mctsData.nodes_searched || '?'} nodes · {mctsData.iterations || '?'} DDS · {mctsData.time_sec || '?'}s
      </Typography>
      {candidates.map((c, i) => (
        <BarRow key={i} candidate={c} barVal={barValues[i]} maxVal={maxVal}
          color={barColors[i] || '#b0bec5'} isAlphaMu
          inherited={typeof c.precision === 'string' && c.precision.includes('inherited')} />
      ))}
    </Box>
  )
}

// DD 候选对比条：bar = scoring_val / avg_tricks；标题行并入样本来源与三分类统计；
// 支持按"全赢/临界/全输"子集筛选查看，切换后按子集决策值重新排序
export function DdBars({ mctsData, scoringMode, ddStats }) {
  const { colorMuted } = usePanelColors()
  const [subset, setSubset] = useState('all')
  const candidates = mctsData.candidates || []
  // 牌局切换时重置筛选（避免上一局的"全赢/临界"残留导致新牌局子集缺数据显示空白）
  useEffect(() => { setSubset('all') }, [mctsData])
  if (!candidates.length) return null
  const mode = scoringMode || (candidates[0] && candidates[0].scoring_mode) || 'avg_tricks'
  const hasSubsets = !!(candidates[0] && candidates[0].subsets)
  const useSubset = subset !== 'all' && hasSubsets

  // 按当前筛选子集计算展示值（tricks/imp/rate）+ 决策值（排序/条宽）；方向已由后端归一
  const rows = candidates.map(c => {
    const s = useSubset ? (c.subsets && c.subsets[subset]) : null
    let tricks, imp, rate, val, mn, mx
    if (useSubset) {
      tricks = s ? s.tricks : null
      imp = s ? s.imp : null
      rate = s ? s.rate : null
      val = s ? s.val : null
      mn = s ? s.mn : null
      mx = s ? s.mx : null
    } else {
      // 新格式优先；旧记录（无 imp_val/make_rate_val）回退到 scoring_val（imp 制等价）
      tricks = c.avg_tricks
      imp = c.imp_val != null ? c.imp_val : (mode === 'imp' ? (c.scoring_val ?? null) : null)
      rate = c.make_rate_val
      mn = c.min_tricks
      mx = c.max_tricks
      val = (hasSubsets && c.subsets && c.subsets.all && c.subsets.all.val != null)
        ? c.subsets.all.val
        : mode === 'imp'
          ? (c.scoring_val || 0)
          : mode === 'make_rate'
            ? (c.scoring_val || 0) * 100
            : (c.avg_tricks || 0)
    }
    return { card: c.card, tricks, imp, rate, val, mn, mx }
  })
  const sorted = [...rows].sort((a, b) => (b.val ?? -Infinity) - (a.val ?? -Infinity))
  const barValues = sorted.map(r => (r.val ?? 0) * (mode === 'make_rate' ? 100 : 1))
  const maxVal = Math.max(...barValues.map(v => Math.abs(v)), 0.01)
  const allVals = sorted.map(r => r.val ?? 0)
  const vmin = Math.min(0, ...allVals)
  const vmax = Math.max(0, ...allVals)
  const barColors = ['#1976d2', '#42a5f5', '#90caf9', '#bbdefb', '#e3f2fd']

  let statsTxt = ''
  if (ddStats) {
    const s = typeof ddStats === 'string' ? JSON.parse(ddStats) : ddStats
    if (s) statsTxt = ` · 全赢${s.sure_win ?? 0}·临界${s.critical ?? 0}·全输${s.sure_lose ?? 0}`
  }

  return (
    <Box sx={{ mt: 0.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
        <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, mb: 0.25, display: 'block' }}>
          DDMC: {mctsData.source ? `（${mctsData.source}）` : ''} {mctsData.iterations}次搜索 · {mctsData.time_sec}s · {mctsData.iters_per_sec}it/s · 剩{mctsData.remaining_cards}张 · {mode === 'imp' ? 'IMP制' : mode === 'make_rate' ? '成约率制' : '赢墩制'}{statsTxt}
        </Typography>
        {hasSubsets && (
          <ToggleButtonGroup size="small" exclusive value={subset} onChange={(e, v) => v && setSubset(v)}
            sx={{ '& .MuiToggleButton-root': { fontSize: '0.6rem', py: 0, px: 0.75, textTransform: 'none' } }}>
            <ToggleButton value="all">全部</ToggleButton>
            <ToggleButton value="win">全赢</ToggleButton>
            <ToggleButton value="crit">临界</ToggleButton>
            <ToggleButton value="lose">全输</ToggleButton>
          </ToggleButtonGroup>
        )}
      </Box>
      {sorted.map((r, i) => (
        <BarRow key={i} candidate={{ card: r.card }} barVal={barValues[i]} maxVal={maxVal}
          color={(barColors[i] || '#e3f2fd').toString()} showDdMode ddScoringMode={mode}
          ddTricks={r.tricks} ddImp={r.imp} ddRate={r.rate} ddMn={r.mn} ddMx={r.mx}
          vmin={vmin} vmax={vmax} />
      ))}
    </Box>
  )
}

// αμ 时间监控区块
export function AlphaMuTiming({ mctsData }) {
  const { isDark, colorMuted } = usePanelColors()
  const ts = mctsData.timing_stats
  if (!Array.isArray(ts) || ts.length === 0) return null
  const totalEval = ts.reduce((s, t) => s + (t.evaluated || 0), 0)
  const totalInh = ts.reduce((s, t) => s + (t.inherited || 0), 0)
  return (
    <Box sx={{ mt: 0.75, p: 0.5, borderRadius: 0.5, bgcolor: isDark ? 'rgba(255,255,255,0.03)' : '#fafafa', border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#eee'}` }}>
      <Typography variant="caption" sx={{ fontSize: '0.65rem', color: colorMuted, fontWeight: 600, display: 'block', mb: 0.25 }}>
        ⏱ 时间监控 · {ts.length}次迭代 · 累计评估{totalEval}候选 · 继承{totalInh}
      </Typography>
      {ts.map((t, i) => {
        const cutInfo = (t.root_cut_at && t.root_cut_at > 0) ? ` · RootCut@${t.root_cut_at}` : ''
        const inhInfo = (t.inherited || 0) > 0 ? ` · 继承${t.inherited}` : ''
        return (
          <Box key={i} sx={{ mt: 0.25 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="caption" sx={{ fontSize: '0.65rem', color: isDark ? '#e0e0e0' : '#333', fontWeight: 500 }}>
                M={t.M} · {t.time_sec}s · {t.dds_calls} DDS · {t.evaluated}/{t.total_candidates}评估{inhInfo}{cutInfo}
              </Typography>
              <Typography variant="caption" sx={{ fontSize: '0.6rem', color: colorMuted }}>
                {t.nodes || 0} nodes
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 0.25, mt: 0.15, height: 4 }}>
              <Box sx={{ flex: t.time_sec || 1, height: '100%', bgcolor: '#7b1fa2', borderRadius: 0.5, minWidth: 2 }} title={`耗时 ${t.time_sec}s`} />
              <Box sx={{ flex: t.dds_calls || 1, height: '100%', bgcolor: '#26a69a', borderRadius: 0.5, minWidth: 2 }} title={`DDS ${t.dds_calls}次`} />
            </Box>
          </Box>
        )
      })}
      <Box sx={{ display: 'flex', gap: 1, mt: 0.4, justifyContent: 'flex-end' }}>
        <Typography variant="caption" sx={{ fontSize: '0.6rem', color: '#7b1fa2' }}>■ 耗时</Typography>
        <Typography variant="caption" sx={{ fontSize: '0.6rem', color: '#26a69a' }}>■ DDS调用</Typography>
      </Box>
    </Box>
  )
}