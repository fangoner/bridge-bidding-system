import { useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, Divider, Button, ToggleButtonGroup, ToggleButton, useTheme, Chip, Collapse, IconButton } from '@mui/material'
import { KeyboardArrowDown, KeyboardArrowRight } from '@mui/icons-material'
import { getSuitColor } from '../constants/suits'
import { PANEL_LAYOUT } from '../styles/constants'
import { formatTotalTime } from '../utils/format'
import { useAIProgress } from '../context/AIProgressContext'
import { EngineView } from './play/engineViews'

function PlayDetailPanel({
  isMobile,
  playState,
  aiPlayHistory,
  aiLoading,
  isPaused,
  onResume,
  onResetPlay,
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
  reviewCursor,
  onReviewPrev,
  onReviewNext,
  onRewindToTrick,
  onReviewCompletedPlay,
  onBackToBidding,
  playTotalTime, // v1.61：打牌总耗时（秒，打牌完成时计算）
  playEngine, // P1-10：当前打牌引擎（估算AI单张出牌预计耗时）
  playStartTime, // P1-10：打牌开始时间戳（打牌中实时显示本局已进行时长）
}) {
  const aiProgress = useAIProgress() // 任务化轮询实时进度文案（AI出牌阶段）
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [viewMode, setViewMode] = useState('output')
  const [collapsed, setCollapsed] = useState(false)
  const prevIsPausedRef = useRef(isPaused)

  // P1 修复：AI 出牌等待中显示"已等待 N 秒"（setState 仅发生在 interval 回调内）
  const aiWaitStartRef = useRef(0)
  const [aiWaitSeconds, setAiWaitSeconds] = useState(0)
  useEffect(() => {
    if (!aiLoading) return
    aiWaitStartRef.current = Date.now()
    const timer = setInterval(() => {
      setAiWaitSeconds(Math.floor((Date.now() - aiWaitStartRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [aiLoading])

  // P1-10：本局实时计时（未完成时每秒刷新"已进行时长"；setState 仅发生在异步回调内）
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  useEffect(() => {
    const complete = playState?.phase === 'complete'
    if (complete || !playStartTime) return
    const update = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - playStartTime) / 1000)))
    const reset = setTimeout(update, 0)
    const timer = setInterval(update, 1000)
    return () => { clearTimeout(reset); clearInterval(timer) }
  }, [playState?.phase, playStartTime])

  // P1-10：按引擎估算 AI 单张出牌预计耗时区间（秒）
  const aiExpectedRange = (() => {
    switch (playEngine) {
      case 'llm': return [10, 40]
      case 'dd': return [5, 25]
      case 'perfect': return [1, 5]
      case 'alphamu': return [5, 25]
      default: return null
    }
  })()
  const aiOverExpected = aiExpectedRange && aiWaitSeconds > aiExpectedRange[1]

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

  // 渲染AI输出卡片的通用组件
  const renderAIOutputCard = (record, showClose = false, onCloseExternal = null) => {
    if (!record) {
      return (
        <Box sx={{ textAlign: 'center', mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            等待AI出牌{aiWaitSeconds > 0 ? `...（已等待 ${aiWaitSeconds}s` : '...（等待中'}
            {aiExpectedRange ? `，预计 ${aiExpectedRange[0]}~${aiExpectedRange[1]}s` : ''}
            {'）'}
          </Typography>
          {aiProgress && (
            <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: '#1976d2', fontSize: '0.7rem' }}>
              {aiProgress}
            </Typography>
          )}
          {aiOverExpected && (
            <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: '#e65100', fontSize: '0.7rem' }}>
              已超过预计耗时，可能正在进行深度计算或 LLM 思考，请耐心等待…
            </Typography>
          )}
        </Box>
      )
    }

    const fullOutput = record.full_output || {}

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
          ) : record.used_engine === 'alphamu' ? (
            <Typography variant="caption" sx={{ color: '#7b1fa2', fontSize: '0.7rem', fontWeight: 500 }}>
              αμ
            </Typography>
          ) : record.used_model && (
            <Typography variant="caption" sx={{ color: colorMuted, fontSize: '0.7rem' }}>
                            {(() => {
                const MODEL_LABELS = {
                  'deepseek-v4-flash': 'deepseek-flash',
                  'deepseek-flash': 'deepseek-flash',
                  'deepseek-v4-pro': 'deepseek-flash',
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
            {(record.used_engine || '') === 'llm' && (
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
            )}
            {showClose && (
              <Button size="small" onClick={() => {
                setSelectedRecord(null)
                if (onCloseExternal) onCloseExternal()
              }}>关闭</Button>
            )}
          </Box>
        </Box>
        
        <EngineView record={record} fullOutput={fullOutput} viewMode={viewMode} />
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
          {!isComplete && playStartTime != null && playInitiated && (
            <Chip size="small" color="info" variant="outlined"
              label={`⏱ 本局已进行：${formatTotalTime(elapsedSeconds)}${aiExpectedRange ? ` · AI单张预计 ${aiExpectedRange[0]}~${aiExpectedRange[1]}s` : ''}`}
              sx={{ fontSize: '0.6rem', height: 22, whiteSpace: 'nowrap', maxWidth: 240 }} />
          )}
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
          {isComplete && !isHistoryRecord && onReviewCompletedPlay && (
            <Button variant="contained" color="primary" onClick={onReviewCompletedPlay} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 48, py: 0.2 }}>复盘</Button>
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

      {/* v1.61：打牌结束后显示打牌总耗时 */}
      {isComplete && playTotalTime != null && (
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5, flexShrink: 0 }}>
          <Chip size="small" color="success" variant="outlined" label={`⏱ 打牌总耗时：${formatTotalTime(playTotalTime)}`} sx={{ fontSize: '0.7rem', height: 22 }} />
        </Box>
      )}

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
