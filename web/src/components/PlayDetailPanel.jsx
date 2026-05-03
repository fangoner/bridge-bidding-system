import { useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, Chip, Divider, CircularProgress, Button, Card as MuiCard, ToggleButtonGroup, ToggleButton, useTheme } from '@mui/material'
import { SUIT_COLOR_MAP } from '../constants/suits'

function PlayDetailPanel({
  isMobile,
  playState,
  aiPlayHistory,
  selectedCard,
  onCardSelect,
  onConfirmPlay,
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
}) {
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [viewMode, setViewMode] = useState('output')  // 'output' or 'input'
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
            {record.position}家 - {record.card?.suit}{record.card?.rank}
          </Typography>
          {(record.used_engine || '') === 'dd' ? (
            <Typography variant="caption" sx={{ color: '#1565c0', fontSize: '0.7rem', fontWeight: 500 }}>
              DD
            </Typography>
          ) : record.used_engine === 'mcts' ? (
            <Typography variant="caption" sx={{ color: '#2e7d32', fontSize: '0.7rem', fontWeight: 500 }}>
              MCTS
            </Typography>
          ) : record.used_engine === 'hybrid' ? (
            <Typography variant="caption" sx={{ color: '#7b1fa2', fontSize: '0.7rem', fontWeight: 500 }}>
              Hybrid
            </Typography>
          ) : record.used_model && (
            <Typography variant="caption" sx={{ color: colorMuted, fontSize: '0.7rem' }}>
              {record.used_model === 'deepseek-v4-pro' ? 'V4-Pro' : 'V4-Flash'}
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
            {(record.used_engine === 'mcts' || (record.used_engine || '') === 'dd' || record.used_engine === 'hybrid') && (() => {
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
          <Typography color="text.secondary" variant="body2">无手牌数据</Typography>
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
        <Typography variant="subtitle2" gutterBottom sx={{ fontSize: '0.85rem' }}>
          {currentPlayer === playState?.dummy
            ? `${playState?.contract?.declarer}家替明手${currentPlayer}家出牌`
            : `${currentPlayer}家出牌`
          }
          {selectedCard ? ' (再次点击确认)' : ' (点击选择)'}
        </Typography>
        <Paper sx={{ 
          p: 0.5, 
          bgcolor: isDark ? 'rgba(255, 253, 231, 0.12)' : '#fffde7', 
          border: isDark ? '2px solid rgba(255, 193, 7, 0.4)' : '2px solid #ffc107',
        }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
            {currentHand.map((card, idx) => {
              const isPlayable = playableCards.some(
                c => c.suit === card.suit && c.rank === card.rank
              )
              const isSelected = selectedCard?.suit === card.suit && 
                                 selectedCard?.rank === card.rank
              
              const color = SUIT_COLOR_MAP[card.suit] || '#000'
              
              return (
                <MuiCard
                  key={idx}
                  onClick={() => handleCardClick(card)}
                  sx={{
                    width: 32,
                    height: 42,
                    cursor: isPlayable ? 'pointer' : 'default',
                    bgcolor: isSelected 
                      ? (isDark ? 'rgba(25, 118, 210, 0.25)' : '#bbdefb') 
                      : (isPlayable ? (isDark ? 'rgba(30, 41, 59, 0.9)' : '#fff') : (isDark ? 'rgba(255,255,255,0.05)' : '#f5f5f5')),
                    border: isSelected ? '2px solid #1976d2' : (isDark ? '1px solid rgba(255,255,255,0.15)' : '1px solid #ddd'),
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.15s',
                    opacity: isPlayable ? 1 : 0.5,
                    '&:hover': isPlayable ? {
                      bgcolor: '#bbdefb',
                      transform: 'translateY(-2px)',
                    } : {},
                  }}
                >
                  <Typography sx={{ color, fontSize: '0.8rem', fontWeight: 500 }}>
                    {card.suit}{card.rank}
                  </Typography>
                </MuiCard>
              )
            })}
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
              const color = SUIT_COLOR_MAP[card.suit] || '#000'
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
                    bgcolor: isSelected ? '#bbdefb' : 'white',
                    px: 0.25,
                    borderRadius: 0.25,
                    border: isSelected ? '1px solid #1976d2' : '1px solid #ddd',
                    cursor: canClick ? 'pointer' : 'default',
                    '&:hover': canClick ? { bgcolor: '#e3f2fd' } : {}
                  }}
                >
                  <Typography variant="caption" sx={{ color: '#666', fontSize: '0.7rem' }}>{pos}:</Typography>
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
      width: isMobile ? '100%' : '600px',
      height: '640px',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5, flexShrink: 0, minHeight: 40 }}>
        <Typography variant="h6" sx={{ fontSize: '1rem', color: isDark ? '#e2e8f0' : undefined }}>打牌详情</Typography>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
          <Chip 
            label={`${contract?.level || '?'}${contract?.suit || 'NT'}`} 
            color="primary" 
            size="small"
            sx={{ fontSize: '0.75rem' }}
          />
          <Chip 
            label={`庄家: ${contract?.declarer || '?'}`} 
            variant="outlined" 
            size="small"
            sx={{ fontSize: '0.75rem' }}
          />
          {dummy && (
            <Chip 
              label={`明手: ${dummy}`} 
              variant="outlined" 
              size="small"
              sx={{ fontSize: '0.75rem' }}
            />
          )}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa', borderRadius: 2, border: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd', minHeight: 0, p: 1 }}>
        <Box sx={{ display: 'flex', gap: 1, mb: 1, flexShrink: 0 }}>
          <Paper sx={{ p: 0.5, bgcolor: isDark ? 'rgba(99, 102, 241, 0.15)' : '#e3f2fd', textAlign: 'center', minWidth: 50 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>庄家方</Typography>
            <Typography variant="body2" fontWeight="bold" color="primary">{declarerTricks}</Typography>
          </Paper>
          <Paper sx={{ p: 0.5, bgcolor: isDark ? 'rgba(255, 152, 0, 0.1)' : '#fff3e0', textAlign: 'center', minWidth: 50 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>防守方</Typography>
            <Typography variant="body2" fontWeight="bold" color="warning.main">{defenderTricks}</Typography>
          </Paper>
          <Paper sx={{ p: 0.5, bgcolor: isDark ? 'rgba(255,255,255,0.05)' : '#f5f5f5', textAlign: 'center', minWidth: 50 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>需要</Typography>
            <Typography variant="body2" fontWeight="bold">{contract?.tricks_needed || '?'}</Typography>
          </Paper>
          {/* 开始/暂停/继续 + 撤销 + 重新打牌按钮，右对齐 */}
          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', ml: 'auto' }}>
            {!isComplete && !playInitiated && (
              <Button
                variant="outlined"
                color="success"
                onClick={onBeginPlay}
                disabled={aiLoading}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                开始
              </Button>
            )}
            {!isComplete && playInitiated && isPaused && (isHistoryRecord || !isHumanTurn || isStartOfTrick) && (
              <Button
                variant="outlined"
                color="primary"
                onClick={onResume}
                disabled={aiLoading}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                继续
              </Button>
            )}
            {!isComplete && playInitiated && !isPaused && !isHumanTurn && (
              <Button
                variant="outlined"
                color="warning"
                onClick={onPausePlay}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                暂停
              </Button>
            )}
            {((!isComplete && playStarted) || (isComplete && !isHistoryRecord)) && onUndoPlay && (
              <Button
                variant="outlined"
                color="secondary"
                onClick={onUndoPlay}
                disabled={aiLoading}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                撤销
              </Button>
            )}
            {onSave && (
              <Button
                variant="outlined"
                color="info"
                size="small"
                onClick={onSave}
                disabled={!canSave}
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                保存
              </Button>
            )}
            {onResetPlay && (
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={onResetPlay}
                disabled={aiLoading}
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                重新打牌
              </Button>
            )}
          </Box>
        </Box>

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
