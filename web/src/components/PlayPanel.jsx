import { useState, useEffect, useRef } from 'react'
import {
  Box,
  Paper,
  Typography,
  Button,
  Chip,
  Divider,
  CircularProgress,
  Alert,
  Card as MuiCard,
  IconButton,
  Tooltip,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import PauseIcon from '@mui/icons-material/Pause'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'

const SUIT_SYMBOLS = {
  spades: '♠',
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
}

const SUIT_COLORS = {
  spades: '#000',
  hearts: '#e53935',
  diamonds: '#e53935',
  clubs: '#000',
}

function PlayPanel({
  playState,
  onPlayCard,
  loading,
  aiLoading,
  onBack,
  isPaused,
  onPauseToggle,
}) {
  const [selectedCard, setSelectedCard] = useState(null)
  const prevPlayerRef = useRef(playState?.current_player)
  
  useEffect(() => {
    if (playState?.current_player !== prevPlayerRef.current) {
      prevPlayerRef.current = playState?.current_player
      setSelectedCard(null)
    }
  }, [playState?.current_player])
  
  if (!playState) {
    return (
      <Paper sx={{ p: 2, textAlign: 'center', width: '600px' }}>
        <Typography color="text.secondary">打牌未初始化</Typography>
      </Paper>
    )
  }
  
  const {
    contract,
    hands,
    dummy,
    current_player,
    declarer_tricks,
    defender_tricks,
    phase,
    current_trick,
    tricks,
    is_human_turn,
    player_roles,
  } = playState
  
  const isComplete = phase === 'complete'
  const trump = contract?.suit
  
  const getPlayableCards = (position) => {
    if (!hands[position]) return []
    
    const hand = hands[position]
    
    if (!current_trick?.cards || current_trick.cards.length === 0) {
      return hand
    }
    
    const leadSuit = current_trick.cards[0][1].suit
    const sameSuit = hand.filter(c => c.suit === leadSuit)
    
    return sameSuit.length > 0 ? sameSuit : hand
  }
  
  const currentHand = hands[current_player] || []
  const playableCards = getPlayableCards(current_player)
  
  const isHumanControlled = (position) => {
    if (position === dummy) {
      return player_roles?.[contract?.declarer] === 'human'
    }
    return player_roles?.[position] === 'human'
  }
  
  const canSelect = is_human_turn && !isComplete && !aiLoading
  
  const handleCardClick = (card) => {
    if (!canSelect) return
    
    const isPlayable = playableCards.some(
      c => c.suit === card.suit && c.rank === card.rank
    )
    
    if (isPlayable) {
      setSelectedCard(card)
    }
  }
  
  const handlePlayCard = () => {
    if (selectedCard && current_player) {
      onPlayCard(current_player, selectedCard)
    }
  }
  
  const renderCurrentTrick = () => {
    const containerStyle = {
      height: '55px',
      display: 'flex',
      alignItems: 'center',
      gap: 1.5,
    }
    
    const renderCardWithTooltip = (pos, card, idx, trickData) => {
      const isAI = trickData.is_ai_cards?.[idx] === true
      const reason = trickData.ai_reasons?.[idx]
      const risk = trickData.ai_risks?.[idx]
      
      const tooltipContent = isAI && (reason || risk) ? (
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
      ) : null
      
      const cardElement = (
        <Paper
          sx={{
            p: 0.8,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            minWidth: 50,
            minHeight: 45,
            bgcolor: isAI ? '#f0f0f0' : '#fff',
            border: isAI ? '1px solid #bbb' : '1px solid #ddd',
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
            {pos}
          </Typography>
          <Typography sx={{ 
            color: SUIT_COLORS[Object.keys(SUIT_SYMBOLS).find(k => SUIT_SYMBOLS[k] === card.suit)] || '#000',
            fontWeight: 'bold',
            fontSize: '1rem',
          }}>
            {card.suit}{card.rank}
          </Typography>
        </Paper>
      )
      
      if (tooltipContent) {
        return (
          <Tooltip key={idx} title={tooltipContent} arrow placement="top">
            {cardElement}
          </Tooltip>
        )
      }
      return <Box key={idx}>{cardElement}</Box>
    }
    
    // 如果当前墩有牌，显示当前墩
    if (current_trick?.cards && current_trick.cards.length > 0) {
      return (
        <Box sx={containerStyle}>
          {current_trick.cards.map(([pos, card], idx) => 
            renderCardWithTooltip(pos, card, idx, current_trick)
          )}
        </Box>
      )
    }
    
    // 如果暂停且刚完成一墩，显示最后一墩的牌
    if (isPaused && tricks && tricks.length > 0) {
      const lastTrick = tricks[tricks.length - 1]
      if (lastTrick?.cards && lastTrick.cards.length === 4) {
        return (
          <Box sx={{ ...containerStyle, flexWrap: 'wrap' }}>
            {lastTrick.cards.map(([pos, card], idx) => 
              renderCardWithTooltip(pos, card, idx, lastTrick)
            )}
            <Chip 
              label={`赢家: ${lastTrick.winner || '?'}`} 
              size="small" 
              color="primary"
            />
          </Box>
        )
      }
    }
    
    return (
      <Box sx={containerStyle}>
        <Typography color="text.secondary" variant="body2">
          等待出牌...
        </Typography>
      </Box>
    )
  }
  
  const renderCompletedTricks = () => {
    if (!tricks || tricks.length === 0) return null
    
    const getTrickDetail = (trick) => {
      if (!trick.cards || trick.cards.length === 0) return '无出牌记录'
      return trick.cards.map(([pos, card]) => `${pos}: ${card.suit}${card.rank}`).join(' → ')
    }
    
    return (
      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          已完成墩 ({tricks.length}/13)
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          {tricks.map((trick, idx) => {
            const isDeclarerSide = trick.winner === contract?.declarer || trick.winner === dummy
            return (
              <Tooltip key={idx} title={getTrickDetail(trick)} arrow placement="top">
                <Chip
                  label={`${idx + 1}: ${trick.winner || '?'}`}
                  size="small"
                  color={isDeclarerSide ? 'primary' : 'default'}
                  variant={isDeclarerSide ? 'filled' : 'outlined'}
                  sx={isDeclarerSide ? { color: 'white', '& .MuiChip-label': { color: 'white' } } : {}}
                />
              </Tooltip>
            )
          })}
        </Box>
      </Box>
    )
  }
  
  const renderCardSelector = () => {
    if (isComplete) {
      return (
        <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography color="text.secondary" variant="body2">
            打牌已结束
          </Typography>
        </Box>
      )
    }
    
    const humanControlled = isHumanControlled(current_player)
    
    return (
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexShrink: 0 }}>
          <Typography variant="subtitle2">
            {current_player}家出牌
          </Typography>
          <Chip 
            label={humanControlled ? '人类' : 'AI'} 
            size="small" 
            color={humanControlled ? 'primary' : 'default'}
            variant="outlined"
          />
          {!is_human_turn && (
            <Typography variant="caption" color="text.secondary">
              (等待AI)
            </Typography>
          )}
        </Box>
        <Paper sx={{ 
          p: 1, 
          bgcolor: is_human_turn ? '#fffde7' : '#fafafa', 
          border: is_human_turn ? '2px solid #ffc107' : '1px solid #ddd',
          flex: 1,
          overflow: 'hidden'
        }}>
          <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 0.5, alignItems: 'center' }}>
            {currentHand.map((card, idx) => {
              const isPlayable = playableCards.some(
                c => c.suit === card.suit && c.rank === card.rank
              )
              const isSelected = selectedCard?.suit === card.suit && 
                                 selectedCard?.rank === card.rank
              
              const canClick = canSelect && isPlayable
              
              const suitName = Object.keys(SUIT_SYMBOLS).find(
                key => SUIT_SYMBOLS[key] === card.suit
              ) || card.suit
              const color = SUIT_COLORS[suitName] || '#000'
              
              return (
                <MuiCard
                  key={idx}
                  onClick={() => handleCardClick(card)}
                  sx={{
                    width: 38,
                    height: 48,
                    cursor: canClick ? 'pointer' : 'default',
                    bgcolor: isSelected ? '#bbdefb' : (isPlayable ? '#fff' : '#f5f5f5'),
                    border: isSelected ? '2px solid #1976d2' : '1px solid #ddd',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.15s',
                    opacity: isPlayable ? 1 : 0.5,
                    flexShrink: 0,
                    '&:hover': canClick ? {
                      bgcolor: '#bbdefb',
                      transform: 'translateY(-2px)',
                    } : {},
                  }}
                >
                  <Typography sx={{ color, fontSize: '0.95rem', fontWeight: 500 }}>
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
  
  return (
    <Paper sx={{ 
      p: 2, 
      width: '600px', 
      height: '680px',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {/* 头部 - 固定高度 */}
      <Box sx={{ 
        mb: 1.5, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        flexShrink: 0,
        height: '40px'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {onBack && (
            <Tooltip title="返回叫牌">
              <IconButton onClick={onBack} size="small">
                <ArrowBackIcon />
              </IconButton>
            </Tooltip>
          )}
          <Typography variant="h6">
            打牌阶段
          </Typography>
          {!isComplete && onPauseToggle && (
            <Tooltip title={isPaused ? "继续" : "暂停"}>
              <IconButton onClick={onPauseToggle} size="small" color={isPaused ? "primary" : "default"}>
                {isPaused ? <PlayArrowIcon /> : <PauseIcon />}
              </IconButton>
            </Tooltip>
          )}
          {isPaused && (
            <Chip label="已暂停" color="warning" size="small" />
          )}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'nowrap' }}>
          <Chip 
            label={`${contract?.level || '?'}${contract?.suit || '?'}`} 
            color="primary" 
            size="small"
          />
          <Chip 
            label={`庄家: ${contract?.declarer || '?'}`} 
            variant="outlined" 
            size="small"
          />
          {trump && trump !== 'NT' && (
            <Chip 
              label={`将牌: ${trump}`} 
              color="secondary" 
              size="small"
            />
          )}
          <Chip 
            label={`明手: ${dummy || '?'}`} 
            variant="outlined" 
            size="small"
          />
        </Box>
      </Box>
      
      <Divider sx={{ my: 1, flexShrink: 0 }} />
      
      {/* 墩数统计 - 固定高度 */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: 2, 
        mb: 1.5,
        flexShrink: 0,
        height: '50px'
      }}>
        <Paper sx={{ p: 0.5, bgcolor: '#e3f2fd', textAlign: 'center', minWidth: '70px', height: '40px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.7rem' }}>庄家方</Typography>
          <Typography variant="h6" fontWeight="bold" color="primary">
            {declarer_tricks}
          </Typography>
        </Paper>
        <Paper sx={{ p: 0.5, bgcolor: '#fff3e0', textAlign: 'center', minWidth: '70px', height: '40px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.7rem' }}>防守方</Typography>
          <Typography variant="h6" fontWeight="bold" color="warning.main">
            {defender_tricks}
          </Typography>
        </Paper>
        <Paper sx={{ p: 0.5, bgcolor: '#f5f5f5', textAlign: 'center', minWidth: '70px', height: '40px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.7rem' }}>需要</Typography>
          <Typography variant="h6" fontWeight="bold">
            {contract?.tricks_needed || '?'}
          </Typography>
        </Paper>
      </Box>
      
      {/* 当前墩 - 固定高度 */}
      <Box sx={{ mb: 3.5, flexShrink: 0, height: '75px' }}>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 0.5, fontSize: '0.85rem' }}>
          当前墩
        </Typography>
        {renderCurrentTrick()}
      </Box>
      
      {/* 出牌选择 - 固定高度 */}
      <Box sx={{ mb: 1.5, flexShrink: 0, height: '90px', overflow: 'hidden' }}>
        {renderCardSelector()}
      </Box>
      
      <Divider sx={{ my: 1, flexShrink: 0 }} />
      
      {/* 操作按钮 - 固定高度 */}
      <Box sx={{ 
        display: 'flex', 
        gap: 2, 
        alignItems: 'center', 
        mb: 1,
        flexShrink: 0,
        height: '32px'
      }}>
        {!isComplete && (
          <>
            {is_human_turn ? (
              <>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handlePlayCard}
                  disabled={!selectedCard || loading || aiLoading}
                  size="small"
                >
                  出牌 {selectedCard ? `${selectedCard.suit}${selectedCard.rank}` : ''}
                </Button>
                {aiLoading && <CircularProgress size={24} />}
              </>
            ) : (
              <>
                <Typography color="text.secondary" variant="body2">
                  等待 {current_player} (AI) 出牌...
                </Typography>
                {aiLoading && <CircularProgress size={24} />}
              </>
            )}
          </>
        )}
      </Box>
      
      {/* 已完成墩 - 可滚动 */}
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {renderCompletedTricks()}
      </Box>
      
      {isComplete && (
        <Alert severity="success" sx={{ mt: 1, flexShrink: 0 }}>
          打牌结束！
        </Alert>
      )}
    </Paper>
  )
}

export default PlayPanel
