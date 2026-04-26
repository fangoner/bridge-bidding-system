import { useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, Chip, Divider, CircularProgress, Button, Card as MuiCard, ToggleButtonGroup, ToggleButton } from '@mui/material'
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
  
  const contract = playState?.contract
  const dummy = playState?.dummy
  const tricks = playState?.tricks || []
  const declarerTricks = playState?.declarer_tricks || 0
  const defenderTricks = playState?.defender_tricks || 0
  const currentPlayer = playState?.current_player
  const isHumanTurn = playState?.is_human_turn
  const isComplete = playState?.phase === 'complete'
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

    // 输出模式的字段定义
    const fields = [
      { key: '推理过程', label: '推理过程', color: 'text.primary', multiline: true },
      { key: '立场分析', label: '立场分析', color: '#1976d2' },
      { key: '核心逻辑', label: '核心逻辑', color: '#2e7d32' },
      { key: '全局规划', label: '全局规划', color: '#00838f', multiline: true },
      { key: '风险提示', label: '风险提示', color: '#ed6c02' },
      { key: '后续路线建议', label: '后续路线', color: '#7b1fa2', multiline: true },
    ]

    // 兼容旧字段名
    const getValue = (key) => {
      return fullOutput[key] || record[key] || ''
    }

    return (
      <Box sx={{ p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.85rem' }}>
            {record.position}家 - {record.card?.suit}{record.card?.rank}
          </Typography>
          {record.used_model && (
            <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem' }}>
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
          fields.map(({ key, label, color, multiline }) => {
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
                      mt: 0.25, p: 0.5, background: '#f8f9fa', borderRadius: 1,
                      fontSize: '0.75rem', lineHeight: 1.3,
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                      border: '1px solid #e9ecef', maxHeight: '120px', overflow: 'auto',
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
          })
        ) : (
          // 输入模式：显示传给AI的完整提示词
          prompt ? (
            <Box component="pre" sx={{ 
              p: 0.75, background: '#f8f9fa', borderRadius: 1,
              fontSize: '0.7rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: '1px solid #e9ecef', maxHeight: '400px', overflow: 'auto',
            }}>
              {prompt}
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

    if (isPaused) {
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
          {currentPlayer}家出牌 {selectedCard ? '(再次点击确认)' : '(点击选择)'}
        </Typography>
        <Paper sx={{ 
          p: 0.5, 
          bgcolor: '#fffde7', 
          border: '2px solid #ffc107',
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
                    bgcolor: isSelected ? '#bbdefb' : (isPlayable ? '#fff' : '#f5f5f5'),
                    border: isSelected ? '2px solid #1976d2' : '1px solid #ddd',
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
            bgcolor: isCurrentTrick ? '#f3e5f5' : (isDeclarerSide ? '#e3f2fd' : '#fff3e0'),
            borderRadius: 0.5,
            border: isCurrentTrick ? '1px dashed #9c27b0' : 'none',
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
              const canClick = isPaused && aiRecord
              
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
      bgcolor: isMobile ? '#f5f5f5' : '#e8e8e8',
      width: isMobile ? '100%' : '600px',
      height: '640px',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5, flexShrink: 0, minHeight: 40 }}>
        <Typography variant="h6" sx={{ fontSize: '1rem' }}>打牌详情</Typography>
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

      <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: '#fafafa', borderRadius: 2, border: '1px solid #ddd', minHeight: 0, p: 1 }}>
        <Box sx={{ display: 'flex', gap: 1, mb: 1, flexShrink: 0 }}>
          <Paper sx={{ p: 0.5, bgcolor: '#e3f2fd', textAlign: 'center', minWidth: 50 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>庄家方</Typography>
            <Typography variant="body2" fontWeight="bold" color="primary">{declarerTricks}</Typography>
          </Paper>
          <Paper sx={{ p: 0.5, bgcolor: '#fff3e0', textAlign: 'center', minWidth: 50 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>防守方</Typography>
            <Typography variant="body2" fontWeight="bold" color="warning.main">{defenderTricks}</Typography>
          </Paper>
          <Paper sx={{ p: 0.5, bgcolor: '#f5f5f5', textAlign: 'center', minWidth: 50 }}>
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
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                开始
              </Button>
            )}
            {!isComplete && playStarted && isPaused && (
              <Button
                variant="outlined"
                color="primary"
                onClick={onResume}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                继续
              </Button>
            )}
            {((!isComplete && playStarted && isPaused) || isComplete) && onUndoPlay && (
              <Button
                variant="outlined"
                color="secondary"
                onClick={onUndoPlay}
                size="small"
                sx={{ fontSize: '0.75rem', textTransform: 'none' }}
              >
                撤销
              </Button>
            )}
            {!isComplete && playStarted && !isPaused && (
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
            {onResetPlay && (
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={onResetPlay}
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
