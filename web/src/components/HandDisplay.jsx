import React from 'react'
import { Box, Typography, useTheme } from '@mui/material'
import { styled } from '@mui/material/styles'
import { getSuitColor } from '../constants/suits'

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme, isActive, isHuman, isPartner }) => ({
  background: 'transparent',
  backdropFilter: 'none',
  borderRadius: 12,
  padding: theme.spacing(1),
  boxShadow: 'none',
  width: '100%',
  fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
  fontWeight: 600,
  transition: 'all 0.25s ease',
  border: 'none',
  color: theme.palette.text.primary,
  ...(isActive && {
    boxShadow: `0 0 0 2px ${theme.palette.primary.main}, 0 4px 12px ${theme.palette.mode === 'dark' ? 'rgba(129,140,248,0.25)' : 'rgba(99,102,241,0.15)'}`,
    border: `1px solid ${theme.palette.primary.main}`,
  }),
}));

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  marginBottom: theme.spacing(0.5),
  color: theme.palette.text.primary,
  fontSize: '0.8rem',
  letterSpacing: '0.01em',
}));

const SuitLine = styled(Box)(({ theme }) => ({
  fontSize: '1rem',
  lineHeight: 1.3,
  whiteSpace: 'nowrap',
  display: 'flex',
  alignItems: 'center',
  gap: '3px',
}));

const SuitSymbol = styled('span', {
  shouldForwardProp: (prop) => prop !== 'suitColor',
})(({ theme, suitColor }) => ({
  fontSize: '1.1rem',
  fontWeight: 700,
  width: '16px',
  textAlign: 'center',
  flexShrink: 0,
}));

const HiddenHand = styled(Box)(({ theme }) => ({
  height: '100%',
  minHeight: '50px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.palette.text.disabled,
}))

const HCPBadge = styled(Box)(({ theme }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '2px 8px',
  borderRadius: 12,
  background: theme.palette.mode === 'dark'
    ? 'rgba(255, 255, 255, 0.08)'
    : 'rgba(0, 0, 0, 0.06)',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: theme.palette.text.secondary,
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
            opacity: isPlayed ? 0.55 : 1,
            color: color,
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
                <Box component="span" sx={{ color, fontWeight: 500, display: 'inline-flex', gap: '3px' }}>
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
