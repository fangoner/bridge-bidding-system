import { useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, Chip, Divider, CircularProgress, Button, Card as MuiCard, ToggleButtonGroup, ToggleButton, TextField, useTheme, IconButton, Tooltip } from '@mui/material'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import { getSuitColor } from '../constants/suits'
import { PANEL_LAYOUT } from '../styles/constants'
import { getDDHints } from '../services/api'

function PlayDetailPanel({
  isMobile,
  playState,
  aiPlayHistory,
  selectedCard,
  onCardSelect,
  onConfirmPlay,
  onManualPlay,
  loading,
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
}) {
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [viewMode, setViewMode] = useState('output')
  const [manualCardInput, setManualCardInput] = useState('')
  const [showDDHints, setShowDDHints] = useState(() => {
    try {
      const saved = localStorage.getItem('bridge_showDDHints')
      return saved !== null ? saved === 'true' : true // 默认开启
    } catch { return true }
  })

  // 持久化 showDDHints 偏好
  const toggleDDHints = () => {
    setShowDDHints(prev => {
      const next = !prev
      try { localStorage.setItem('bridge_showDDHints', String(next)) } catch {}
      return next
    })
  }
  const [ddHints, setDDHints] = useState(null)
  const [ddHintsLoading, setDDHintsLoading] = useState(false)
  const prevIsPausedRef = useRef(isPaused)
  
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
  const declarerTricks = playState?.declarer_tricks || 0
  const defenderTricks = playState?.defender_tricks || 0
  const currentPlayer = playState?.current_player
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

  // 轮到人类出牌时自动获取DD提示
  useEffect(() => {
    if (showDDHints && isHumanTurn && playState) {
      setDDHintsLoading(true)
      getDDHints()
        .then(data => {
          if (data.success) {
            setDDHints(data.hints)
          } else {
            setDDHints(null)
          }
        })
        .catch(() => setDDHints(null))
        .finally(() => setDDHintsLoading(false))
    } else {
      setDDHints(null)  // 关闭提示或非人类回合时清除
    }
  }, [isHumanTurn, showDDHints, playState?.current_trick?.cards?.length])

  const isStartOfTrick = (playState?.current_trick?.cards?.length || 0) === 0
  const currentHand = playState?.hands?.[currentPlayer] || []
  
  const getPlayableCards = () => {
    if (!currentHand || currentHand.length === 0) return []
    const currentTrick = playState?.current_trick
    if (!currentTrick?.cards || currentTrick.cards.length === 0) {
      return currentHand
    }
    const leadSuit = currentTrick.cards[0][1].suit
    const sameSuit = currentHand.filter(c => c.suit === leadSuit)
    return sameSuit.length > 0 ? sameSuit : currentHand
  }
  
  const playableCards = getPlayableCards()

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
      midgame: '中盘DD',
      midgame_mcts: '中盘MCTS',
      critical: '关键LLM',
      critical_mcts: '关键LLM',
      endgame: '残局DD',
    }
    const tieredPhaseLabel = TIERED_PHASE_LABELS[fullOutput.tiered_phase] || ''

    // 输出模式的字段定义（v1.38 精简：局面评估+候选对比+核心逻辑）
    const fields = [
      { key: '候选对比', label: '抉择过程', color: 'text.primary', multiline: true },
      { key: '核心逻辑', label: '核心逻辑', color: '#2e7d32' },
      { key: '局面评估', label: '局面评估', color: '#1976d2', multiline: true },
    ]

    // 兼容旧字段名，确保旧记录也能显示；防御性转为字符串避免React渲染报错
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
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.85rem' }}>
            {record.position}家 -{' '}
            <Typography component="span" sx={{ color: getSuitColor(record.card?.suit, isDark), fontWeight: 'bold', fontSize: '0.85rem' }}>
              {record.card?.suit}{record.card?.rank}
            </Typography>
          </Typography>
          {(record.used_engine || '') === 'perfect' ? (
            <Typography variant="caption" sx={{ color: '#6a1b9a', fontSize: '0.7rem', fontWeight: 500 }}>
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
          ) : record.used_engine === 'tiered' ? (
            <Typography variant="caption" sx={{ color: '#e65100', fontSize: '0.7rem', fontWeight: 500 }}>
              Tiered·{tieredPhaseLabel}
            </Typography>
          ) : record.used_model && (
            <Typography variant="caption" sx={{ color: colorMuted, fontSize: '0.7rem' }}>
              {record.used_model === 'deepseek-v4-pro' ? 'V4-Pro' : 'V4-Flash'}
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
            {fields.filter(({ key }) => {
              const isNonLLM = record.used_engine && record.used_engine !== 'llm'
              if (!isNonLLM) return true
              return key !== '候选对比' && key !== '核心逻辑'
            }).map(({ key, label, color, multiline }) => {
              const value = getValue(key)
              if (!value) return null
              return (
                <Box key={key} sx={{ mt: 0.5 }}>
                  {multiline ? (
                    <Box>
                      <Typography variant="body2" sx={{ fontSize: '0.8rem', color, fontWeight: 500 }}>
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
                    <Typography variant="body2" sx={{ fontSize: '0.8rem', color }}>
                      <strong>{label}:</strong> {value}
                    </Typography>
                  )}
                </Box>
              )
            })}
            {(record.used_engine === 'mcts' || (record.used_engine || '') === 'dd' || record.used_engine === 'tiered' || record.used_engine === 'perfect') && (() => {
              try {
                const mctsRaw = fullOutput.mcts_stats
                if (!mctsRaw) { console.log('[MCTS] no mcts_stats in fullOutput'); return null }
                const mctsData = typeof mctsRaw === 'string' ? JSON.parse(mctsRaw) : mctsRaw
                const candidates = mctsData.candidates
                if (!candidates || candidates.length === 0) { console.log('[MCTS] no candidates'); return null }
                const isDD = (record.used_engine || '') === 'dd' || candidates[0].samples !== undefined

                // MCTS: bar width = visits比例; DD: bar width = avg_tricks比例
                const barValues = candidates.map(c => isDD ? (c.avg_tricks || 0) : (c.visits || 0))
                const maxVal = Math.max(...barValues.map(v => Math.abs(v)), 0.01)
                const barColors = ['#1976d2', '#42a5f5', '#90caf9', '#bbdefb', '#e3f2fd']
                console.log('[MCTS] rendering bars:', mctsData.iterations, 'candidates:', candidates.length)
                return (
                  <Box key="mcts" sx={{ mt: 0.75 }}>
                    <Typography variant="caption" sx={{ fontSize: '0.7rem', color: colorMuted, mb: 0.25, display: 'block' }}>
                      {isDD ? 'DDMC' : 'MCTS'}: {mctsData.iterations}次搜索 · {mctsData.time_sec}s · {mctsData.iters_per_sec}it/s · 剩{mctsData.remaining_cards}张
                    </Typography>
                    {candidates.map((c, i) => (
                      <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.15 }}>
                        <Typography variant="caption" sx={{ minWidth: 28, fontSize: '0.7rem', fontWeight: 600, color: isDark ? '#e0e0e0' : '#333' }}>
                          {c.card}
                        </Typography>
                        <Box sx={{ flex: 1, height: 12, bgcolor: isDark ? 'rgba(255,255,255,0.06)' : '#eee', borderRadius: 0.5, overflow: 'hidden' }}>
                          <Box sx={{
                            width: `${(Math.abs(barValues[i]) / maxVal) * 100}%`,
                            height: '100%',
                            bgcolor: barColors[i] || '#90caf9',
                            borderRadius: 0.5,
                            transition: 'width 0.3s',
                          }} />
                        </Box>
                        <Typography variant="caption" sx={{ minWidth: 68, fontSize: '0.65rem', color: colorMuted, textAlign: 'right' }}>
                          {isDD ? `${c.avg_tricks}墩 [${c.min_tricks}-${c.max_tricks}]` : `${c.visits}次 · ${c.avg_tricks}墩`}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                )
              } catch (e) { console.error('[MCTS] viz error:', e); return null }
            })()}
          </>
        ) : (
          // 输入模式：显示传给AI的完整提示词
          prompt ? (
            <Box>
              <Typography variant="caption" sx={{ display: 'block', color: colorMuted, fontSize: '0.7rem', mb: 0.25 }}>
                提示词长度: {prompt.length.toLocaleString()} 字符
                &nbsp;·&nbsp;约 {(estimateTokens(prompt)).toLocaleString()} token
              </Typography>
              <Box component="pre" sx={{ 
                p: 0.75, background: bgCode, borderRadius: 1,
                fontSize: '0.7rem', lineHeight: 1.4,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                border: '1px solid #e9ecef', maxHeight: '400px', overflow: 'auto',
              }}>
                {prompt}
              </Box>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
              无输入数据
            </Typography>
          )
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

  const renderCardSelector = () => {
    if (isComplete) {
      return (
        <Box sx={{ textAlign: 'center', py: 1 }}>
          <Typography color="text.secondary" variant="body2">打牌已结束</Typography>
        </Box>
      )
    }

    // 每墩开始前隐藏选牌面板，显示开始/继续按钮
    if (!playInitiated || (isPaused && isStartOfTrick)) {
      return null
    }

    if (isPaused && !isHumanTurn) {
      return null
    }

    if (!isHumanTurn) {
      return null
    }

    if (currentHand.length === 0) {
      return (
        <Box sx={{ textAlign: 'center', py: 1 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {playState?.current_player}家出牌 — 直接输入牌张
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', justifyContent: 'center' }}>
            <TextField
              size="small"
              placeholder="如 ♠A 或 S A"
              value={manualCardInput}
              onChange={(e) => setManualCardInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && manualCardInput.trim()) {
                  onManualPlay?.(playState?.current_player, manualCardInput.trim())
                  setManualCardInput('')
                }
              }}
              sx={{ width: 140, '& input': { fontSize: '0.85rem', textAlign: 'center' } }}
            />
            <Button
              variant="contained"
              size="small"
              disabled={!manualCardInput.trim()}
              onClick={() => {
                onManualPlay?.(playState?.current_player, manualCardInput.trim())
                setManualCardInput('')
              }}
            >
              出牌
            </Button>
          </Box>
        </Box>
      )
    }

    const handleCardClick = (card) => {
      const isPlayable = playableCards.some(
        c => c.suit === card.suit && c.rank === card.rank
      )
      if (!isPlayable) return

      // 如果点击的是已选中的牌，确认出牌
      if (selectedCard?.suit === card.suit && selectedCard?.rank === card.rank) {
        onConfirmPlay()
      } else {
        // 否则选中该牌
        onCardSelect(card)
      }
    }

    return (
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
          <Typography variant="subtitle2" sx={{ fontSize: '0.85rem' }}>
            {currentPlayer === playState?.dummy
              ? `${playState?.contract?.declarer}家替明手${currentPlayer}家出牌`
              : `${currentPlayer}家出牌`
            }
            {selectedCard ? ' (再次点击确认)' : ' (点击选择)'}
          </Typography>
          <Tooltip title={showDDHints ? '隐藏DD提示' : '显示DD提示'} arrow>
            <IconButton size="small" onClick={toggleDDHints} sx={{ p: 0.3 }}>
              {showDDHints ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
          {ddHintsLoading && <CircularProgress size={14} />}
        </Box>
        <Paper sx={{
          p: 0.5,
          bgcolor: isDark ? 'rgba(255, 253, 231, 0.08)' : '#fffde7',
          border: isDark ? '2px solid rgba(255, 193, 7, 0.3)' : '2px solid #ffc107',
        }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
            {(() => {
              const playableSet = new Set(playableCards.map(c => c.suit + c.rank))
              return currentHand.map((card, idx) => {
              const isPlayable = playableSet.has(card.suit + card.rank)
              const isSelected = selectedCard?.suit === card.suit && 
                                 selectedCard?.rank === card.rank
              
              const color = getSuitColor(card.suit, isDark)

              const hintKey = card.suit + card.rank
              const hint = ddHints?.[hintKey]

              return (
                <Box key={idx} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.2 }}>
                  <MuiCard
                    onClick={() => handleCardClick(card)}
                    sx={{
                      width: 32,
                      height: 38,
                      cursor: isPlayable ? 'pointer' : 'default',
                      bgcolor: isSelected
                        ? (isDark ? 'rgba(66, 165, 245, 0.35)' : '#bbdefb')
                        : (isPlayable ? (isDark ? 'rgba(255,255,255,0.12)' : '#fff') : (isDark ? 'rgba(255,255,255,0.04)' : '#f5f5f5')),
                      border: isSelected ? '2px solid #42a5f5' : (isDark ? '1px solid rgba(255,255,255,0.2)' : '1px solid #ddd'),
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.15s',
                      opacity: isPlayable ? 1 : 0.5,
                      '&:hover': isPlayable ? {
                        bgcolor: isDark ? 'rgba(66, 165, 245, 0.45)' : '#bbdefb',
                        transform: 'translateY(-2px)',
                      } : {},
                    }}
                  >
                    <Typography sx={{ color, fontSize: '0.8rem', fontWeight: 500 }}>
                      {card.suit}{card.rank}
                    </Typography>
                  </MuiCard>
                  {hint !== undefined && (
                    <Typography sx={{
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      color: hint === '='
                        ? (isDark ? '#66bb6a' : '#2e7d32')
                        : hint.startsWith('+')
                          ? (isDark ? '#42a5f5' : '#1565c0')
                          : (isDark ? '#ef5350' : '#c62828'),
                      lineHeight: 1,
                    }}>
                      {hint}
                    </Typography>
                  )}
                </Box>
              )
            })})()}
          </Box>
        </Paper>
      </Box>
    )
  }

  const renderCompletedTricks = () => {
    // 合并已完成的墩和当前墩进行中的牌
    const currentTrick = playState?.current_trick
    const currentTrickCards = currentTrick?.cards || []
    
    // 构建完整的出牌列表：已完成墩 + 当前墩（进行中）
    const allTricks = [...tricks]
    if (currentTrickCards.length > 0) {
      // 当前墩未完成，构造一个"进行中"的墩对象
      allTricks.push({
        cards: currentTrickCards,
        leader: currentTrick?.leader,
        winner: null, // 未完成，无赢家
        isCurrentTrick: true,
      })
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
            border: isCurrentTrick ? (isDark ? '1px dashed rgba(156, 39, 176, 0.5)' : '1px dashed #9c27b0') : 'none',
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 'bold', fontSize: '0.75rem', minWidth: 35 }}>
            {isCurrentTrick ? `${idx + 1}:...` : `${idx + 1}:${trick.winner || '?'}`}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.25 }}>
            {trick.cards && trick.cards.map(([pos, card], cardIdx) => {
              const color = getSuitColor(card.suit, isDark)
              const aiRecord = getAIRecordForCard(pos, card)
              const isSelected = selectedRecord === aiRecord
              const canClick = !!aiRecord
              
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
                    bgcolor: isSelected ? (isDark ? 'rgba(25, 118, 210, 0.3)' : '#bbdefb') : (isDark ? 'rgba(255,255,255,0.08)' : 'white'),
                    px: 0.25,
                    borderRadius: 0.25,
                    border: isSelected ? '1px solid #1976d2' : (isDark ? '1px solid rgba(255,255,255,0.12)' : '1px solid #ddd'),
                    cursor: canClick ? 'pointer' : 'default',
                    '&:hover': canClick ? { bgcolor: isDark ? 'rgba(255,255,255,0.15)' : '#e3f2fd' } : {}
                  }}
                >
                  <Typography variant="caption" sx={{ color: isDark ? '#94a3b8' : '#666', fontSize: '0.7rem' }}>{pos}:</Typography>
                  <Typography sx={{ color, fontSize: '0.75rem', fontWeight: 500 }}>{card.suit}{card.rank}</Typography>
                </Box>
              )
            })}
          </Box>
        </Box>
      )
    }

    return (
      <Box sx={{ mt: 1 }}>
        <Typography variant="subtitle2" gutterBottom sx={{ fontSize: '0.75rem' }}>
          出牌记录 ({tricks.length}/13)
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            {allTricks.slice(0, 7).map((trick, idx) => renderTrickRow(trick, idx))}
          </Box>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            {allTricks.slice(7).map((trick, idx) => renderTrickRow(trick, idx + 7))}
          </Box>
        </Box>
      </Box>
    )
  }

  return (
    <Paper elevation={3} sx={{ 
      p: 1, 
      bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : (isMobile ? '#f5f5f5' : '#e8e8e8'),
      minWidth: isMobile ? undefined : PANEL_LAYOUT.minWidth,
      maxWidth: isMobile ? undefined : PANEL_LAYOUT.maxWidth,
      flex: isMobile ? undefined : '1 1 0%',
      width: isMobile ? '100%' : undefined,
      height: `${PANEL_LAYOUT.height}px`,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {/* 标题栏：打牌详情 + 墩数统计 + 操作按钮在一行 */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5, flexShrink: 0, minHeight: 36, flexWrap: 'wrap' }}>
        <Typography variant="h6" sx={{ fontSize: '0.95rem', color: isDark ? '#e2e8f0' : undefined }}>打牌详情</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
            庄家方 <strong style={{ color: theme.palette.primary.main }}>{declarerTricks}</strong>
          </Typography>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
            防守方 <strong style={{ color: theme.palette.warning.main }}>{defenderTricks}</strong>
          </Typography>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
            需要 <strong>{contract?.tricks_needed || '?'}</strong>
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
          {!isComplete && !playInitiated && (
            <Button variant="outlined" color="success" onClick={onBeginPlay} disabled={aiLoading} size="small" sx={{ fontSize: '0.7rem', textTransform: 'none', minWidth: 40, py: 0.2 }}>开始</Button>
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
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa', borderRadius: 2, border: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd', minHeight: 0, p: 1 }}>

        <Box sx={{ flex: 2, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
          {renderAIOutput()}
        </Box>

        <Divider sx={{ my: 1, flexShrink: 0 }} />

        <Box sx={{ flexShrink: 0 }}>
          {renderCardSelector()}
          {renderCompletedTricks()}
        </Box>
      </Box>
    </Paper>
  )
}

export default PlayDetailPanel
