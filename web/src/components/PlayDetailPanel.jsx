import { useState, useEffect, useRef, useMemo } from 'react'
import { Box, Typography, Paper, Divider, Button, ToggleButtonGroup, ToggleButton, useTheme, Chip, Collapse, IconButton } from '@mui/material'
import { KeyboardArrowDown, KeyboardArrowRight } from '@mui/icons-material'
import { getSuitColor } from '../constants/suits'
import { PANEL_LAYOUT } from '../styles/constants'

function PlayDetailPanel({
  isMobile,
  playState,
  aiPlayHistory,
  aiLoading,
  isPaused,
  onResume,
  onResetPlay,
  height = '680px',
  externalSelectedRecord,
  onClearExternalRecord,
  playStarted,
  onBeginPlay,
  onPausePlay,
  playInitiated,
  onUndoPlay,
  isHistoryRecord = false,
  positionRoles,
  onSave,
  canSave,
  imageOpeningLead,
  reviewCursor,
  onReviewPrev,
  onReviewNext,
  onRewindToTrick,
  onBackToBidding,
}) {
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [viewMode, setViewMode] = useState('output')
  const [collapsed, setCollapsed] = useState(false)
  const prevIsPausedRef = useRef(isPaused)

  // 恢复继续时清除选中记录
  useEffect(() => {
    if (prevIsPausedRef.current && !isPaused) {
      setTimeout(() => setSelectedRecord(null), 0)
    }
    prevIsPausedRef.current = isPaused
  }, [isPaused])

  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const bgWhite = isDark ? 'rgba(30, 41, 59, 0.7)' : 'white'
  const bgCode = isDark ? 'rgba(255,255,255,0.05)' : '#f8f9fa'
  const borderCode = isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid #e9ecef'
  const colorMuted = isDark ? '#94a3b8' : '#888'
  
  const contract = playState?.contract
  const dummy = playState?.dummy
  const tricks = playState?.tricks || []
  const isHumanTurn = (() => {
    const cp = playState?.current_player
    if (!cp || !positionRoles) return false
    // 明手时由庄家操作
    if (cp === playState?.dummy) {
      return positionRoles[playState?.contract?.declarer] === 'human'
    }
    return positionRoles[cp] === 'human'
  })()
  const isComplete = playState?.phase === 'complete'
  const isStartOfTrick = (playState?.current_trick?.cards?.length || 0) === 0

  // 估算token数（中文字符≈1 token，其他≈4字符/token）
  const estimateTokens = (text) => {
    if (!text) return 0
    let chinese = 0
    let other = 0
    for (const ch of text) {
      if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) chinese++
      else other++
    }
    return Math.ceil(chinese + other / 4)
  }

  // 渲染AI输出卡片的通用组件
  const renderAIOutputCard = (record, showClose = false, onCloseExternal = null) => {
    if (!record) {
      return (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 2 }}>
          等待AI出牌...
        </Typography>
      )
    }

    const fullOutput = record.full_output || {}
    const prompt = record.prompt || ''

    // Tiered 阶段标签
    const TIERED_PHASE_LABELS = {
      opening_lead: '首攻',
      dummy_reveal: '明手亮开',
      first_trick: '第一墩',
      first_trick_third: '第一墩·三家',
      first_trick_fourth: '第一墩·四家',
      midgame: '中盘DD',
      midgame_mcts: '中盘MCTS',
      critical: '关键LLM',
      critical_mcts: '关键LLM',
      endgame: '残局DD',
      endgame_alpha_mu: '残局αμ',
    }
    const tieredPhaseLabel = TIERED_PHASE_LABELS[fullOutput.tiered_phase] || ''

    // 输出模式：显示 fullOutput 中所有有效字段（排除内部/已渲染的）
    const SKIP_KEYS = ['mcts_stats', 'tiered_phase', 'tiered_dd_fallback', 'tiered_mcts_fallback', 'validation_warning', 'llm_review']
    const FIELD_COLORS = ['#e65100', 'text.primary', '#2e7d32', '#1976d2', '#37474f', '#1565c0']
    const fields = Object.keys(fullOutput)
      .filter(k => !SKIP_KEYS.includes(k) && fullOutput[k] != null && fullOutput[k] !== '')
      .map((k, i) => ({
        key: k,
        label: k,
        color: FIELD_COLORS[i % FIELD_COLORS.length],
        multiline: typeof fullOutput[k] === 'string' && fullOutput[k].length > 40,
      }))
    // dd_hint 确保在最前面
    if (fullOutput.dd_hint && !fields.find(f => f.key === 'dd_hint')) {
      fields.unshift({ key: 'dd_hint', label: 'DD注入', color: '#e65100', multiline: true })
    }

    const getValue = (key) => {
      const val = fullOutput[key] || record[key]
      if (val === null || val === undefined) return ''
      if (typeof val === 'string') return val
      if (typeof val === 'object') return JSON.stringify(val, null, 2)
      return String(val)
    }

    return (
      <Box sx={{ p: 1.5, background: bgWhite, borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', overflow: viewMode === 'input' ? 'hidden' : undefined }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.75rem' }}>
            {record.position}家 -{' '}
            <Typography component="span" sx={{ color: getSuitColor(record.card?.suit, isDark), fontWeight: 'bold', fontSize: '0.75rem' }}>
              {record.card?.suit}{record.card?.rank}
            </Typography>
          </Typography>
          {(record.used_engine || '') === 'perfect' ? (
            <Typography variant="caption" sx={{ color: '#37474f', fontSize: '0.7rem', fontWeight: 500 }}>
              DD·完美
            </Typography>
          ) : (record.used_engine || '') === 'dd' ? (
            <Typography variant="caption" sx={{ color: '#1565c0', fontSize: '0.7rem', fontWeight: 500 }}>
              DD
            </Typography>
          ) : record.used_engine === 'mcts' ? (
            <Typography variant="caption" sx={{ color: '#2e7d32', fontSize: '0.7rem', fontWeight: 500 }}>
              MCTS
            </Typography>
          ) : record.used_engine === 'alphamu' ? (
            <Typography variant="caption" sx={{ color: '#7b1fa2', fontSize: '0.7rem', fontWeight: 500 }}>
              αμ
            </Typography>
          ) : record.used_engine === 'alphamu_llm' ? (
            <Typography variant="caption" sx={{ color: '#6a1b9a', fontSize: '0.7rem', fontWeight: 500 }}>
              {(() => {
                const MODEL_LABELS = {
                  'deepseek-v4-flash': 'V4-Flash',
                  'deepseek-v4-pro': 'V4-Pro',
                  'doubao-seed-2.1-pro': '豆包Pro',
                  'doubao-seed-2.1-turbo': '豆包Turbo',
                }
                const base = (record.used_model || '').replace('::reasoning', '')
                const label = MODEL_LABELS[base] || base || 'LLM'
                const isReasoning = (record.used_model || '').includes('::reasoning')
                return `αμ+${label}${isReasoning ? '·思考' : '·快答'}`
              })()}
            </Typography>
          ) : record.used_engine === 'tiered' ? (
            <Typography variant="caption" sx={{ color: '#e65100', fontSize: '0.7rem', fontWeight: 500 }}>
              Tiered·{tieredPhaseLabel}
            </Typography>
          ) : record.used_model && (
            <Typography variant="caption" sx={{ color: colorMuted, fontSize: '0.7rem' }}>
                            {(() => {
                const MODEL_LABELS = {
                  'deepseek-v4-flash': 'V4-Flash',
                  'deepseek-v4-pro': 'V4-Pro',
                  'doubao-seed-2.1-pro': '豆包 Pro',
                  'doubao-seed-2.1-turbo': '豆包 Turbo',
                }
                const base = (record.used_model || '').replace('::reasoning', '')
                return MODEL_LABELS[base] || record.used_model
              })()}
            </Typography>
          )}
          {record.elapsed_ms != null && (
            <Typography variant="caption" sx={{ color: colorMuted, fontSize: '0.65rem', ml: 1 }}>
              {record.elapsed_ms >= 1000
                ? `${(record.elapsed_ms / 1000).toFixed(1)}s`
                : `${record.elapsed_ms}ms`}
            </Typography>
          )}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <ToggleButtonGroup
              value={viewMode}
              exclusive
              onChange={(_, v) => v && setViewMode(v)}
              size="small"
              sx={{ height: 24, '& .MuiToggleButton-root': { py: 0, px: 1, fontSize: '0.7rem' } }}
            >
              <ToggleButton value="output" sx={{ textTransform: 'none' }}>输出</ToggleButton>
              <ToggleButton value="input" sx={{ textTransform: 'none' }}>输入</ToggleButton>
            </ToggleButtonGroup>
            {showClose && (
              <Button size="small" onClick={() => {
                setSelectedRecord(null)
                if (onCloseExternal) onCloseExternal()
              }}>关闭</Button>
            )}
          </Box>
        </Box>
        
        {viewMode === 'output' ? (
          // 输出模式：显示AI返回的字段
          <>
            {fields.map(({ key, label, color, multiline }) => {
              const value = getValue(key)
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
            {(record.used_engine === 'mcts' || (record.used_engine || '') === 'dd' || record.used_engine === 'tiered' || record.used_engine === 'perfect' || record.used_engine === 'alphamu' || record.used_engine === 'alphamu_llm') && (() => {
              try {
                const mctsRaw = fullOutput.mcts_stats
                if (!mctsRaw) { console.log('[Stats] no mcts_stats'); return null }
                const mctsData = typeof mctsRaw === 'string' ? JSON.parse(mctsRaw) : mctsRaw
                const candidates = mctsData.candidates
                if (!candidates || candidates.length === 0) { console.log('[Stats] no candidates'); return null }

                const isAlphaMu = mctsData.algorithm === 'alpha_mu'
                const isDD = (record.used_engine || '') === 'dd' || (!isAlphaMu && candidates[0].samples !== undefined)

                // αμ: bar = success_rate (成功率 0-1); DD: bar = avg_tricks; MCTS: bar = visits
                const barValues = candidates.map(c =>
                  isAlphaMu ? ((c.success_rate || 0) * 100) :
                  isDD ? (c.avg_tricks || 0) :
                  (c.visits || 0)
                )
                const maxVal = Math.max(...barValues.map(v => Math.abs(v)), 0.01)
                const barColors = isAlphaMu
                  ? ['#263238', '#37474f', '#546e7a', '#78909c', '#b0bec5']
                  : ['#1976d2', '#42a5f5', '#90caf9', '#bbdefb', '#e3f2fd']
                return (
                  <Box key="stats" sx={{ mt: 0.75 }}>
                    <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, mb: 0.25, display: 'block' }}>
                      {isAlphaMu
                        ? `αμ: ${mctsData.num_worlds || '?'} worlds · depth≤4 · ${mctsData.nodes_searched || '?'} nodes · ${mctsData.iterations || '?'} DDS · ${mctsData.time_sec || '?'}s`
                        : `${isDD ? 'DDMC' : 'MCTS'}: ${mctsData.iterations}次搜索 · ${mctsData.time_sec}s · ${mctsData.iters_per_sec}it/s · 剩${mctsData.remaining_cards}张`
                      }
                    </Typography>
                    {candidates.map((c, i) => {
                      const isInherited = isAlphaMu && typeof c.precision === 'string' && c.precision.includes('inherited')
                      return (
                      <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.15 }}>
                        <Typography variant="caption" sx={{ minWidth: 28, fontSize: '0.7rem', fontWeight: 600, color: isDark ? '#e0e0e0' : '#333' }}>
                          {c.card}
                        </Typography>
                        <Box sx={{ flex: 1, height: 12, bgcolor: isDark ? 'rgba(255,255,255,0.06)' : '#eee', borderRadius: 0.5, overflow: 'hidden' }}>
                          <Box sx={{
                            width: `${(Math.abs(barValues[i]) / maxVal) * 100}%`,
                            height: '100%',
                            bgcolor: barColors[i] || '#90caf9',
                            opacity: isInherited ? 0.45 : 1,
                            borderRadius: 0.5,
                            transition: 'width 0.3s, opacity 0.3s',
                          }} />
                        </Box>
                        <Typography variant="caption" sx={{ minWidth: 110, fontSize: '0.65rem', color: colorMuted, textAlign: 'right' }}>
                          {isAlphaMu
                            ? `${((c.success_rate || 0) * 100).toFixed(0)}% · ${c.avg_tricks ?? '?'}墩 · ${c.success_count || 0}/${c.total_useful || '?'} · front${c.front_size || 1}${isInherited ? ' · 继承' : ''}`
                            : isDD
                              ? `${c.avg_tricks}墩 [${c.min_tricks}-${c.max_tricks}]`
                              : `${c.visits}次 · ${c.avg_tricks}墩`
                          }
                        </Typography>
                      </Box>
                      )
                    })}
                    {isAlphaMu && Array.isArray(mctsData.timing_stats) && mctsData.timing_stats.length > 0 && (() => {
                      const ts = mctsData.timing_stats
                      const maxTime = Math.max(...ts.map(t => t.time_sec || 0), 0.1)
                      const maxDds = Math.max(...ts.map(t => t.dds_calls || 0), 1)
                      const totalEval = ts.reduce((s, t) => s + (t.evaluated || 0), 0)
                      const totalInh = ts.reduce((s, t) => s + (t.inherited || 0), 0)
                      return (
                        <Box sx={{ mt: 0.75, p: 0.5, borderRadius: 0.5, bgcolor: isDark ? 'rgba(255,255,255,0.03)' : '#fafafa', border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#eee'}` }}>
                          <Typography variant="caption" sx={{ fontSize: '0.65rem', color: colorMuted, fontWeight: 600, display: 'block', mb: 0.25 }}>
                            ⏱ 时间监控 · {ts.length}次迭代 · 累计评估{totalEval}候选 · 继承{totalInh}
                          </Typography>
                          {ts.map((t, i) => {
                            const pct = (t.time_sec || 0) / maxTime * 100
                            const ddsPct = (t.dds_calls || 0) / maxDds * 100
                            const cutInfo = (t.root_cut_at && t.root_cut_at > 0)
                              ? ` · RootCut@${t.root_cut_at}`
                              : ''
                            const inhInfo = (t.inherited || 0) > 0
                              ? ` · 继承${t.inherited}`
                              : ''
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
                    })()}
                  </Box>
                )
              } catch (e) { console.error('[Stats] viz error:', e); return null }
            })()}
            {record.used_engine === 'alphamu_llm' && (() => {
              try {
                const reviewRaw = fullOutput.llm_review
                if (!reviewRaw) return null
                const review = typeof reviewRaw === 'string' ? JSON.parse(reviewRaw) : reviewRaw
                const groupIdx = review.group || 0
                const reviewCard = review.card || ''
                const reason = review.reason || ''
                const plan = review.plan || ''
                const planValid = review.plan_valid === true
                const planInvalid = review.plan_valid === false
                const hasGroup = groupIdx > 0 && Boolean(reviewCard)
                let labelColor = '#757575'
                let labelText = '采纳αμ选择'
                if (hasGroup) {
                  labelColor = '#6a1b9a'
                  labelText = `选组${groupIdx}出${reviewCard}（${reason}）`
                } else if (planValid) {
                  labelColor = '#1565c0'
                  labelText = `计划有效: ${plan.length > 48 ? plan.slice(0, 48) + '...' : plan}`
                } else if (planInvalid) {
                  labelColor = '#e65100'
                  labelText = `计划无效: ${plan.length > 48 ? plan.slice(0, 48) + '...' : plan}`
                }
                return (
                  <Box sx={{ mt: 0.5, p: 0.5, borderRadius: 0.5, bgcolor: isDark ? 'rgba(255,255,255,0.04)' : '#f5f5f5' }}>
                    <Typography variant="caption" sx={{ fontSize: '0.65rem', color: labelColor, fontWeight: 500, display: 'block' }}>
                      {labelText}
                    </Typography>
                  </Box>
                )
              } catch (e) { return null }
            })()}
          </>
        ) : (
          // 输入模式：显示传给AI的完整提示词
          (() => {
            // LLM打牌的提示词在 llm_review.llm_prompt 中
            const reviewRaw = fullOutput.llm_review
            const review = reviewRaw && typeof reviewRaw === 'string' ? JSON.parse(reviewRaw) : reviewRaw
            const llmPrompt = review ? review.llm_prompt : null
            const displayPrompt = llmPrompt || prompt
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
          })()
        )}
      </Box>
    )
  }

  const renderAIOutput = () => {
    // 优先使用外部传入的记录（桌面点击的牌）
    if (externalSelectedRecord) {
      return renderAIOutputCard(externalSelectedRecord, true, onClearExternalRecord)
    }

    if (!isPaused) {
      if (selectedRecord) {
        return renderAIOutputCard(selectedRecord, true)
      }
      const latestRecord = aiPlayHistory?.[aiPlayHistory.length - 1]
      return renderAIOutputCard(latestRecord || null)
    }

    if (selectedRecord) {
      return renderAIOutputCard(selectedRecord, true)
    }

    const latestRecord = aiPlayHistory?.[aiPlayHistory.length - 1]
    return renderAIOutputCard(latestRecord || null)
  }

  const renderCompletedTricks = () => {
    // 合并已完成的墩和当前墩进行中的牌
    const currentTrick = playState?.current_trick
    const currentTrickCards = currentTrick?.cards || []

    // 构建完整的出牌列表：已完成墩 + 当前墩（进行中）
    const allTricks = [...tricks]
    if (currentTrickCards.length > 0) {
      allTricks.push({
        cards: currentTrickCards.map(([pos, card]) => [pos, card]),
        leader: currentTrick?.leader,
        winner: null,
        is_ai_cards: currentTrick?.is_ai_cards || [],
        ai_reasons: currentTrick?.ai_reasons || [],
        ai_risks: currentTrick?.ai_risks || [],
        dd_hints: currentTrick?.dd_hints || [],
        isCurrentTrick: true,
      })
    }

    // 总牌数
    const totalCards = allTricks.reduce((s, t) => s + (t.cards?.length || 0), 0)

    // 每墩第一张牌的全局序号
    const trickStartIndices = []
    let accum = 0
    for (const t of allTricks) {
      trickStartIndices.push(accum)
      accum += t.cards?.length || 0
    }

    // 获取DD hint中某张牌的delta
    const getCardDelta = (ddHint, card) => {
      if (!ddHint) return null
      return ddHint[card.suit + card.rank] || null
    }

    // 获取DD hint中最优delta（庄家方视角取最大值）
    const getBestDelta = (ddHint) => {
      if (!ddHint) return null
      const deltas = Object.values(ddHint).map(v => {
        if (v === '=') return 0
        return parseInt(v, 10) || 0
      })
      if (deltas.length === 0) return null
      return Math.max(...deltas)
    }

    if (allTricks.length === 0) return null

    const getAIRecordForCard = (position, card) => {
      if (!aiPlayHistory || aiPlayHistory.length === 0) return null
      const found = aiPlayHistory.find(record => 
        record.position === position && 
        record.card?.suit === card.suit && 
        record.card?.rank === card.rank
      )
      return found
    }

    const renderTrickRow = (trick, idx) => {
      const isCurrentTrick = trick.isCurrentTrick
      const isDeclarerSide = !isCurrentTrick && (trick.winner === contract?.declarer || trick.winner === dummy)
      const globalStartIdx = trickStartIndices[idx]

      return (
        <Box
          key={idx}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            py: 0.25,
            px: 0.5,
            bgcolor: isCurrentTrick
              ? (isDark ? 'rgba(156, 39, 176, 0.15)' : '#f3e5f5')
              : (isDeclarerSide ? (isDark ? 'rgba(99, 102, 241, 0.12)' : '#e3f2fd') : (isDark ? 'rgba(255, 152, 0, 0.1)' : '#fff3e0')),
            borderRadius: 0.5,
            border: isCurrentTrick ? (isDark ? '1px dashed rgba(120, 144, 156, 0.5)' : '1px dashed #546e7a') : 'none',
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 'bold', fontSize: '0.75rem', minWidth: 35 }}>
            {isCurrentTrick ? `${idx + 1}:...` : `${idx + 1}:${trick.winner || '?'}`}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.25, flexWrap: 'wrap' }}>
            {trick.cards && trick.cards.map(([pos, card], cardIdx) => {
              const globalCardIdx = globalStartIdx + cardIdx
              const isBeforeCursor = reviewCursor != null && globalCardIdx < reviewCursor
              const isAtCursor = reviewCursor != null && globalCardIdx === reviewCursor
              const isAfterCursor = reviewCursor != null && globalCardIdx > reviewCursor
              // 游标语义：reviewCursor=N 表示前 N 张已出，第 N 张（globalCardIdx===N）回到手牌（未出）
              // 所以 isAtCursor 和 isAfterCursor 都应灰显
              const isGrayed = isAtCursor || isAfterCursor

              const color = getSuitColor(card.suit, isDark)
              const aiRecord = getAIRecordForCard(pos, card)
              const isSelected = selectedRecord === aiRecord
              const canClick = !!aiRecord

              // DD hint 标签
              const ddHint = trick.dd_hints?.[cardIdx]
              const cardDelta = getCardDelta(ddHint, card)
              const bestDelta = getBestDelta(ddHint)
              const cardDeltaNum = cardDelta === '=' ? 0 : (cardDelta ? parseInt(cardDelta, 10) : null)
              const bestDeltaNum = bestDelta
              const isBest = cardDeltaNum !== null && bestDeltaNum !== null && cardDeltaNum >= bestDeltaNum

              return (
                <Box
                  key={cardIdx}
                  onClick={() => {
                    if (canClick) {
                      setSelectedRecord(aiRecord)
                      if (onClearExternalRecord) onClearExternalRecord()
                    }
                  }}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.1,
                    bgcolor: isAtCursor
                      ? (isDark ? 'rgba(255, 193, 7, 0.35)' : '#fff8e1')
                      : isSelected ? (isDark ? 'rgba(25, 118, 210, 0.3)' : '#bbdefb')
                      : (isDark ? 'rgba(255,255,255,0.08)' : 'white'),
                    px: 0.25,
                    borderRadius: 0.25,
                    border: isAtCursor
                      ? '2px solid #ffc107'
                      : isSelected ? '1px solid #1976d2'
                      : (isDark ? '1px solid rgba(255,255,255,0.12)' : '1px solid #ddd'),
                    cursor: canClick ? 'pointer' : 'default',
                    opacity: isGrayed ? 0.3 : 1,
                    filter: isGrayed ? 'grayscale(0.5)' : 'none',
                    '&:hover': canClick ? { bgcolor: isDark ? 'rgba(255,255,255,0.15)' : '#e3f2fd' } : {},
                    transition: 'opacity 0.2s, filter 0.2s',
                  }}
                >
                  <Typography variant="caption" sx={{ color: isDark ? '#94a3b8' : '#666', fontSize: '0.7rem' }}>{pos}:</Typography>
                  <Typography sx={{ color, fontSize: '0.75rem', fontWeight: 500 }}>{card.suit}{card.rank}</Typography>
                  {cardDelta && (
                    <Chip
                      size="small"
                      label={cardDelta}
                      sx={{
                        fontSize: '0.55rem',
                        height: 14,
                        ml: 0.25,
                        bgcolor: isBest ? (isDark ? 'rgba(76,175,80,0.3)' : '#c8e6c9') : (isDark ? 'rgba(255,152,0,0.3)' : '#ffe0b2'),
                        color: isBest ? '#2e7d32' : '#e65100',
                        '& .MuiChip-label': { px: 0.25 },
                      }}
                    />
                  )}
                </Box>
              )
            })}
          </Box>
        </Box>
      )
    }

    return (
      <Box sx={{ mt: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <IconButton size="small" onClick={() => setCollapsed(!collapsed)} sx={{ p: 0 }}>
              {collapsed ? <KeyboardArrowRight fontSize="small" /> : <KeyboardArrowDown fontSize="small" />}
            </IconButton>
            <Typography variant="subtitle2" sx={{ fontSize: '0.75rem' }}>
              出牌记录 ({tricks.length}/13)
            </Typography>
          </Box>
          {reviewCursor != null && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Button size="small" onClick={onReviewPrev} disabled={reviewCursor === 0}
                sx={{ fontSize: '0.7rem', minWidth: 24, py: 0 }}>◀</Button>
              <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 600, minWidth: 60, textAlign: 'center' }}>
                {reviewCursor}/{totalCards || '?'}张已出
              </Typography>
              <Button size="small" onClick={onReviewNext}
                disabled={reviewCursor >= totalCards}
                sx={{ fontSize: '0.7rem', minWidth: 24, py: 0 }}>▶</Button>
              {onRewindToTrick && (
                <Button size="small" color="warning" variant="outlined"
                  onClick={() => onRewindToTrick(reviewCursor)}
                  sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 52, py: 0 }}>
                  从此重打
                </Button>
              )}
            </Box>
          )}
        </Box>
        <Collapse in={!collapsed}>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
              {allTricks.slice(0, 7).map((trick, idx) => renderTrickRow(trick, idx))}
            </Box>
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
              {allTricks.slice(7).map((trick, idx) => renderTrickRow(trick, idx + 7))}
            </Box>
          </Box>
        </Collapse>
      </Box>
    )
  }

  return (
    <Paper elevation={0} sx={{
      m: 0,
      p: 1,
      background: isDark
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(30, 41, 59, 0.6) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0.7) 100%)',
      backdropFilter: 'blur(20px) saturate(180%)',
      WebkitBackdropFilter: 'blur(20px) saturate(180%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.8)'}`,
      boxShadow: isDark
        ? '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)'
        : '0 8px 32px rgba(79, 70, 229, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.9)',
      borderRadius: 3,
      width: isMobile ? '100%' : '640px',
      height: '640px',
      minHeight: '640px',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      boxSizing: 'border-box'
    }}>
      {/* 标题栏：打牌详情 + 操作按钮 */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5, flexShrink: 0, height: 44, flexWrap: 'nowrap', gap: 0.5, overflow: 'hidden' }}>
        <Typography variant="h6" sx={{ fontSize: '0.95rem', color: isDark ? '#e2e8f0' : undefined, flexShrink: 0 }}>打牌详情</Typography>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexShrink: 0 }}>
          {!isComplete && !playInitiated && (
            <Button variant="outlined" color="success" onClick={onBeginPlay} disabled={aiLoading} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>开始打牌</Button>
          )}
          {!isComplete && playInitiated && isPaused && (isHistoryRecord || !isHumanTurn || isStartOfTrick) && (
            <Button variant="outlined" color="primary" onClick={onResume} disabled={aiLoading} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>继续</Button>
          )}
          {!isComplete && playInitiated && !isPaused && !isHumanTurn && (
            <Button variant="outlined" color="warning" onClick={onPausePlay} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>暂停</Button>
          )}
          {((!isComplete && playStarted) || (isComplete && !isHistoryRecord)) && onUndoPlay && (
            <Button variant="outlined" color="secondary" onClick={onUndoPlay} disabled={aiLoading} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>撤销</Button>
          )}
          {onSave && (
            <Button variant="outlined" color="info" size="small" onClick={onSave} disabled={!canSave} sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>保存</Button>
          )}
          {onResetPlay && (
            <Button variant="outlined" color="error" size="small" onClick={onResetPlay} disabled={aiLoading} sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 56, py: 0.2 }}>重新打牌</Button>
          )}
          {onBackToBidding && (
            <Button variant="outlined" size="small" onClick={onBackToBidding} disabled={aiLoading} sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 56, py: 0.2, color: isDark ? '#94a3b8' : '#666', borderColor: isDark ? '#475569' : '#ccc' }}>返回叫牌</Button>
          )}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa', borderRadius: 2, border: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd', minHeight: 0, p: 1 }}>

        <Box sx={{ flex: 2, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
          {renderAIOutput()}
        </Box>

        <Divider sx={{ my: 1, flexShrink: 0 }} />

        <Box sx={{ flexShrink: 0 }}>
          {renderCompletedTricks()}
        </Box>
      </Box>
    </Paper>
  )
}

export default PlayDetailPanel
