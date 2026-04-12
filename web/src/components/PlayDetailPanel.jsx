import { useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, Chip, Divider, CircularProgress, Button, Card as MuiCard } from '@mui/material'

const SUIT_COLORS = {
  '♠': '#000',
  '♥': '#e53935',
  '♦': '#e53935',
  '♣': '#000',
}

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
  height = '680px',
}) {
  const [selectedRecord, setSelectedRecord] = useState(null)
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

  const renderAIOutput = () => {
    if (!isPaused) {
      if (aiPlayHistory && aiPlayHistory.length > 0) {
        const displayRecord = aiPlayHistory[aiPlayHistory.length - 1]
        const fullOutput = displayRecord.full_output || {}

        return (
          <Box sx={{ p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.85rem' }}>
                {displayRecord.position}家 - {displayRecord.card?.suit}{displayRecord.card?.rank}
              </Typography>
            </Box>
            
            {displayRecord.reasoning && (
              <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
                <strong>理由:</strong> {displayRecord.reasoning}
              </Typography>
            )}
            
            {displayRecord.risk && (
              <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem', color: 'warning.main' }}>
                <strong>风险提示:</strong> {displayRecord.risk}
              </Typography>
            )}
            
            {fullOutput["局面分析"] && (
              <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
                <strong>局面分析:</strong>
                <Box component="pre" sx={{ 
                  mt: 0.5, p: 0.5, background: '#f8f9fa', borderRadius: 1,
                  fontSize: '0.75rem', lineHeight: 1.3,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  border: '1px solid #e9ecef', maxHeight: '100px', overflow: 'auto'
                }}>
                  {fullOutput["局面分析"]}
                </Box>
              </Typography>
            )}
          </Box>
        )
      }
      return (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 2 }}>
          等待AI出牌...
        </Typography>
      )
    }

    if (selectedRecord) {
      const fullOutput = selectedRecord.full_output || {}

      return (
        <Box sx={{ p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.85rem' }}>
              {selectedRecord.position}家 - {selectedRecord.card?.suit}{selectedRecord.card?.rank}
            </Typography>
            <Button size="small" onClick={() => setSelectedRecord(null)}>关闭</Button>
          </Box>
          
          {selectedRecord.reasoning && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
              <strong>理由:</strong> {selectedRecord.reasoning}
            </Typography>
          )}
          
          {selectedRecord.risk && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem', color: 'warning.main' }}>
              <strong>风险提示:</strong> {selectedRecord.risk}
            </Typography>
          )}
          
          {fullOutput["局面分析"] && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
              <strong>局面分析:</strong>
              <Box component="pre" sx={{ 
                mt: 0.5, p: 0.5, background: '#f8f9fa', borderRadius: 1,
                fontSize: '0.75rem', lineHeight: 1.3,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                border: '1px solid #e9ecef', maxHeight: '100px', overflow: 'auto'
              }}>
                {fullOutput["局面分析"]}
              </Box>
            </Typography>
          )}
        </Box>
      )
    }

    if (aiPlayHistory && aiPlayHistory.length > 0) {
      const displayRecord = aiPlayHistory[aiPlayHistory.length - 1]
      const fullOutput = displayRecord.full_output || {}

      return (
        <Box sx={{ p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2', fontSize: '0.85rem' }}>
              {displayRecord.position}家 - {displayRecord.card?.suit}{displayRecord.card?.rank}
            </Typography>
          </Box>
          
          {displayRecord.reasoning && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
              <strong>理由:</strong> {displayRecord.reasoning}
            </Typography>
          )}
          
          {displayRecord.risk && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem', color: 'warning.main' }}>
              <strong>风险提示:</strong> {displayRecord.risk}
            </Typography>
          )}
          
          {fullOutput["局面分析"] && (
            <Typography variant="body2" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
              <strong>局面分析:</strong>
              <Box component="pre" sx={{ 
                mt: 0.5, p: 0.5, background: '#f8f9fa', borderRadius: 1,
                fontSize: '0.75rem', lineHeight: 1.3,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                border: '1px solid #e9ecef', maxHeight: '100px', overflow: 'auto'
              }}>
                {fullOutput["局面分析"]}
              </Box>
            </Typography>
          )}
        </Box>
      )
    }

    return (
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 2 }}>
        等待AI出牌...
      </Typography>
    )
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
      if (isPlayable) {
        onCardSelect(card)
      }
    }

    return (
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ fontSize: '0.85rem' }}>
          {currentPlayer}家出牌 (点击选择)
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
              
              const color = SUIT_COLORS[card.suit] || '#000'
              
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
        <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Button
            variant="contained"
            color="primary"
            onClick={onConfirmPlay}
            disabled={!selectedCard || loading || aiLoading}
            size="small"
          >
            出牌 {selectedCard ? `${selectedCard.suit}${selectedCard.rank}` : ''}
          </Button>
          {(loading || aiLoading) && <CircularProgress size={16} />}
        </Box>
      </Box>
    )
  }

  const renderCompletedTricks = () => {
    if (tricks.length === 0) return null

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
      const isDeclarerSide = trick.winner === contract?.declarer || trick.winner === dummy
      
      return (
        <Box 
          key={idx} 
          sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 0.5,
            py: 0.25,
            px: 0.5,
            bgcolor: isDeclarerSide ? '#e3f2fd' : '#fff3e0',
            borderRadius: 0.5,
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 'bold', fontSize: '0.75rem', minWidth: 35 }}>
            {idx + 1}:{trick.winner || '?'}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.25 }}>
            {trick.cards && trick.cards.map(([pos, card]) => {
              const color = SUIT_COLORS[card.suit] || '#000'
              const aiRecord = getAIRecordForCard(pos, card)
              const isSelected = selectedRecord === aiRecord
              const canClick = isPaused && aiRecord
              
              return (
                <Box 
                  key={pos}
                  onClick={() => canClick && setSelectedRecord(aiRecord)}
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
          已完成墩 ({tricks.length}/13)
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            {tricks.slice(0, 7).map((trick, idx) => renderTrickRow(trick, idx))}
          </Box>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
            {tricks.slice(7).map((trick, idx) => renderTrickRow(trick, idx + 7))}
          </Box>
        </Box>
      </Box>
    )
  }

  return (
    <Paper sx={{ 
      p: 2, 
      width: isMobile ? '100%' : '600px',
      height: height,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1, flexShrink: 0 }}>
        <Typography variant="h6" sx={{ fontSize: '1rem' }}>打牌详情</Typography>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
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
        {isPaused && onResume && (
          <Button
            variant="contained"
            color="primary"
            onClick={onResume}
            size="small"
          >
            继续
          </Button>
        )}
      </Box>

      <Divider sx={{ mb: 1, flexShrink: 0 }} />

      <Box sx={{ flex: 2, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        {renderAIOutput()}
      </Box>

      <Divider sx={{ my: 1, flexShrink: 0 }} />

      <Box sx={{ flexShrink: 0 }}>
        {renderCardSelector()}
        {renderCompletedTricks()}
      </Box>
    </Paper>
  )
}

export default PlayDetailPanel
