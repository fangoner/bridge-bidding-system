import React from 'react'
import { Box, Typography, useTheme } from '@mui/material'
import { styled } from '@mui/material/styles'
import { getSuitColor } from '../constants/suits'

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme, isActive, isHuman, isPartner }) => ({
  background: theme.palette.mode === 'dark' ? 'rgba(30, 41, 59, 0.8)' : 'white',
  borderRadius: 12,
  padding: theme.spacing(1),
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  width: '100%',
  fontFamily: '"SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace',
  transition: 'all 0.25s ease',
  border: '1px solid',
  borderColor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : '#e2e8f0',
  ...(isActive && {
    boxShadow: '0 0 0 2px #6366f1, 0 4px 12px rgba(99, 102, 241, 0.2)',
    transform: 'scale(1.02)',
    borderColor: '#6366f1',
  }),
  ...(isHuman && {
    background: theme.palette.mode === 'dark'
      ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0.08) 100%)'
      : 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
    borderColor: theme.palette.mode === 'dark' ? 'rgba(165, 180, 252, 0.4)' : '#a5b4fc',
  }),
  ...(isPartner && {
    background: theme.palette.mode === 'dark'
      ? 'linear-gradient(135deg, rgba(236, 72, 153, 0.12) 0%, rgba(236, 72, 153, 0.06) 100%)'
      : 'linear-gradient(135deg, #fdf4ff 0%, #fae8ff 100%)',
    borderColor: theme.palette.mode === 'dark' ? 'rgba(232, 121, 249, 0.35)' : '#e879f9',
  }),
}));

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  marginBottom: theme.spacing(0.5),
  color: theme.palette.mode === 'dark' ? '#e2e8f0' : '#1e293b',
  fontSize: '0.8rem',
  letterSpacing: '0.01em',
}));

const SuitLine = styled(Box)(({ theme }) => ({
  fontSize: '0.95rem',
  lineHeight: 1.3,
  whiteSpace: 'nowrap',
  display: 'flex',
  alignItems: 'center',
  gap: '2px',
}));

const SuitSymbol = styled('span', {
  shouldForwardProp: (prop) => prop !== 'suitColor',
})(({ theme, suitColor }) => ({
  fontSize: '1rem',
  fontWeight: 700,
  width: '14px',
  textAlign: 'center',
  flexShrink: 0,
}));

const HiddenHand = styled(Box)(({ theme }) => ({
  height: '100%',
  minHeight: '50px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.palette.mode === 'dark' ? '#64748b' : '#94a3b8',
}))

const HCPBadge = styled(Box)(({ theme }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '2px 8px',
  borderRadius: 12,
  background: theme.palette.mode === 'dark'
    ? 'linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.04) 100%)'
    : 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: theme.palette.mode === 'dark' ? '#94a3b8' : '#475569',
  marginLeft: 'auto',
}));

function HandDisplay({
  hand,
  position,
  isActive = false,
  isHuman = false,
  isDealer = false,
  isPartner = false,
  showContent = true,
  titleExtra = null,
  hideTitle = false,
  playedCards = null,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const hasCards = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs);

  // 将花色字符串转为带标记的单牌数组
  const suitSymbolMap = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' };

  const renderSuitCards = (suitName, suitStr, suitSymbol) => {
    const color = getSuitColor(suitSymbol, isDark)
    if (!suitStr || suitStr === '-') {
      return <Box component="span" sx={{ color, opacity: 0.5 }}>-</Box>
    }

    return suitStr.split('').map((rank, i) => {
      const cardKey = suitSymbol + rank
      const isPlayed = playedCards && playedCards.has(cardKey)
      return (
        <Box
          component="span"
          key={i}
          sx={{
            textDecoration: isPlayed ? 'line-through' : 'none',
            opacity: isPlayed ? 0.38 : 1,
            color: isPlayed ? '#888' : color,
          }}
        >
          {rank}
        </Box>
      )
    })
  }

  return (
    <HandCard
      isActive={isActive}
      isHuman={isHuman}
      isPartner={isPartner}
    >
      {!hideTitle && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
          <HandTitle>
            {position}{isDealer ? '*' : ''}
          </HandTitle>
          {showContent && hasCards && hand.hcp !== undefined && (
            <HCPBadge>{hand.hcp}点</HCPBadge>
          )}
          {titleExtra}
        </Box>
      )}

      {showContent && hasCards ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
          {['spades', 'hearts', 'diamonds', 'clubs'].map(suitName => {
            const symbol = suitSymbolMap[suitName]
            const color = getSuitColor(symbol, isDark)
            return (
              <SuitLine key={suitName}>
                <SuitSymbol suitColor={color} sx={{ color }}>{symbol}</SuitSymbol>
                <Box component="span" sx={{ color, fontWeight: 500 }}>
                  {renderSuitCards(suitName, hand[suitName], symbol)}
                </Box>
              </SuitLine>
            )
          })}
        </Box>
      ) : (
        <HiddenHand>
          <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.8rem' }}>
            {hasCards ? '[隐藏]' : '[待输入]'}
          </Typography>
        </HiddenHand>
      )}
    </HandCard>
  );
}

export default HandDisplay;
