import React from 'react'
import { Box, Typography, Paper, Tooltip, Button, Chip, CircularProgress, Card as MuiCard } from '@mui/material'
import { getSuitColor } from '../constants/suits'

function PlayTable({
  currentTrick,
  tricks,
  contract,
  declarerTricks,
  defenderTricks,
  currentPlayer,
  isHumanTurn,
  isPaused,
  isComplete,
  selectedCard,
  onCardSelect,
  onConfirmPlay,
  loading,
  aiLoading,
  currentHand,
  playableCards,
  onResume,
}) {
  const getCardAtPosition = (position) => {
    if (!currentTrick?.cards) return null
    const cardEntry = currentTrick.cards.find(([pos]) => pos === position)
    return cardEntry ? cardEntry[1] : null
  }

  const getIsAICard = (position) => {
    if (!currentTrick?.is_ai_cards || !currentTrick?.cards) return false
    const idx = currentTrick.cards.findIndex(([pos]) => pos === position)
    return idx >= 0 && currentTrick.is_ai_cards[idx] === true
  }

  const getAIReason = (position) => {
    if (!currentTrick?.ai_reasons || !currentTrick?.cards) return null
    const idx = currentTrick.cards.findIndex(([pos]) => pos === position)
    return idx >= 0 ? currentTrick.ai_reasons[idx] : null
  }

  const getAIRisk = (position) => {
    if (!currentTrick?.ai_risks || !currentTrick?.cards) return null
    const idx = currentTrick.cards.findIndex(([pos]) => pos === position)
    return idx >= 0 ? currentTrick.ai_risks[idx] : null
  }

  const renderCard = (position) => {
    const card = getCardAtPosition(position)
    const isAI = getIsAICard(position)
    const reason = getAIReason(position)
    const risk = getAIRisk(position)

    if (!card) {
      return (
        <Box
          sx={{
            width: 52,
            height: 68,
            border: '2px dashed #ccc',
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: '#fafafa',
          }}
        >
          <Typography variant="caption" color="text.disabled">
            {position}
          </Typography>
        </Box>
      )
    }

    const color = getSuitColor(card.suit)

    const cardElement = (
      <Paper
        sx={{
          width: 52,
          height: 68,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: isAI ? '#f0f0f0' : '#fff',
          border: isAI ? '1px solid #bbb' : '1px solid #ddd',
          boxShadow: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
          {position}
        </Typography>
        <Typography sx={{ color, fontWeight: 'bold', fontSize: '1.1rem' }}>
          {card.suit}{card.rank}
        </Typography>
      </Paper>
    )

    if (isAI && (reason || risk)) {
      const tooltipContent = (
        <Box sx={{ p: 1 }}>
          {reason && (
            <Typography variant="body2" sx={{ mb: risk ? 1 : 0 }}>
              <strong>理由:</strong> {reason}
            </Typography>
          )}
          {risk && (
            <Typography variant="body2" color="warning.main">
              <strong>风险:</strong> {risk}
            </Typography>
          )}
        </Box>
      )
      return (
        <Tooltip title={tooltipContent} arrow placement="top">
          {cardElement}
        </Tooltip>
      )
    }

    return cardElement
  }

  const getLastTrickWinner = () => {
    if (isPaused && tricks && tricks.length > 0) {
      const lastTrick = tricks[tricks.length - 1]
      return lastTrick?.winner
    }
    return null
  }

  const handleCardClick = (card) => {
    if (!isHumanTurn || isComplete || aiLoading) return
    
    const isPlayable = playableCards?.some(
      c => c.suit === card.suit && c.rank === card.rank
    )
    
    if (isPlayable) {
      onCardSelect(card)
    }
  }

  const renderCardSelector = () => {
    if (isComplete) {
      return (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography color="text.secondary">打牌已结束</Typography>
        </Box>
      )
    }

    if (isPaused && !isHumanTurn) {
      return (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography color="text.secondary" sx={{ mb: 1 }}>
            一墩完成，{getLastTrickWinner() || '?'}家赢
          </Typography>
          {onResume && (
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
      )
    }

    if (!isHumanTurn) {
      return (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography color="text.secondary">
            等待 {currentPlayer} (AI) 出牌...
          </Typography>
          {aiLoading && <CircularProgress size={20} sx={{ ml: 1 }} />}
        </Box>
      )
    }

    if (!currentHand || currentHand.length === 0) {
      return (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography color="text.secondary">无手牌数据</Typography>
        </Box>
      )
    }

    return (
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ fontSize: '0.85rem' }}>
          {currentPlayer}家出牌 (点击选择)
        </Typography>
        <Paper sx={{ 
          p: 1, 
          bgcolor: '#fffde7', 
          border: '2px solid #ffc107',
        }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
            {currentHand.map((card, idx) => {
              const isPlayable = playableCards?.some(
                c => c.suit === card.suit && c.rank === card.rank
              )
              const isSelected = selectedCard?.suit === card.suit && 
                                 selectedCard?.rank === card.rank
              
              const canClick = isPlayable
              
              const color = getSuitColor(card.suit)
              
              return (
                <MuiCard
                  key={idx}
                  onClick={() => handleCardClick(card)}
                  sx={{
                    width: 36,
                    height: 46,
                    cursor: canClick ? 'pointer' : 'default',
                    bgcolor: isSelected ? '#bbdefb' : (isPlayable ? '#fff' : '#f5f5f5'),
                    border: isSelected ? '2px solid #1976d2' : '1px solid #ddd',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.15s',
                    opacity: isPlayable ? 1 : 0.5,
                    '&:hover': canClick ? {
                      bgcolor: '#bbdefb',
                      transform: 'translateY(-2px)',
                    } : {},
                  }}
                >
                  <Typography sx={{ color, fontSize: '0.85rem', fontWeight: 500 }}>
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
          {(loading || aiLoading) && <CircularProgress size={20} />}
        </Box>
      </Box>
    )
  }

  return (
    <Paper sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Typography variant="h6">出牌区域</Typography>
        {isPaused && (
          <Chip label="已暂停" color="warning" size="small" />
        )}
        {isComplete && (
          <Chip label="打牌结束" color="success" size="small" />
        )}
      </Box>

      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <Paper sx={{ p: 0.5, bgcolor: '#e3f2fd', textAlign: 'center', minWidth: 60 }}>
          <Typography variant="caption" color="text.secondary">庄家方</Typography>
          <Typography variant="h6" fontWeight="bold" color="primary">{declarerTricks}</Typography>
        </Paper>
        <Paper sx={{ p: 0.5, bgcolor: '#fff3e0', textAlign: 'center', minWidth: 60 }}>
          <Typography variant="caption" color="text.secondary">防守方</Typography>
          <Typography variant="h6" fontWeight="bold" color="warning.main">{defenderTricks}</Typography>
        </Paper>
        <Paper sx={{ p: 0.5, bgcolor: '#f5f5f5', textAlign: 'center', minWidth: 60 }}>
          <Typography variant="caption" color="text.secondary">需要</Typography>
          <Typography variant="h6" fontWeight="bold">{contract?.tricks_needed || '?'}</Typography>
        </Paper>
      </Box>

      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1 }}>
          {renderCard('北')}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4, my: 1 }}>
          {renderCard('西')}
          <Box sx={{ width: 52, height: 68, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {getLastTrickWinner() && (
              <Chip label={`${getLastTrickWinner()}赢`} size="small" color="primary" />
            )}
          </Box>
          {renderCard('东')}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
          {renderCard('南')}
        </Box>
      </Box>

      <Box sx={{ mt: 2 }}>
        {renderCardSelector()}
      </Box>
    </Paper>
  )
}

export default PlayTable
