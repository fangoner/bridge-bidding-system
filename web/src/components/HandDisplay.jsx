import React from 'react'
import { Box, Typography, useTheme, Tooltip } from '@mui/material'
import { styled } from '@mui/material/styles'
import { getSuitColor } from '../constants/suits'

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme }) => ({
  background: 'transparent',
  borderRadius: 12,
  padding: theme.spacing(1),
  boxShadow: 'none',
  width: '100%',
  fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
  fontWeight: 600,
  transition: 'all 0.25s ease',
  border: 'none',
  color: theme.palette.mode === 'dark' ? '#f5f5f5' : '#1a1a1a',
}));

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 700,
  marginBottom: '4px',
  color: theme.palette.mode === 'dark' ? '#f0f0f0' : '#333',
  fontSize: '0.78rem',
  letterSpacing: '0.02em',
}));

const SuitLine = styled(Box)({
  fontSize: '0.98rem',
  lineHeight: 1.3,
  whiteSpace: 'nowrap',
  display: 'flex',
  alignItems: 'center',
  gap: '4px',
});

const SuitSymbol = styled('span')({
  fontSize: '1.05rem',
  fontWeight: 700,
  width: '15px',
  textAlign: 'center',
  flexShrink: 0,
});

const HiddenHand = styled(Box)(({ theme }) => ({
  height: '100%',
  minHeight: '50px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.palette.mode === 'dark' ? '#607080' : '#94a3b8',
}))

const HCPBadge = styled(Box)(({ theme }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '1px 6px',
  borderRadius: 10,
  background: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.12)' : 'rgba(0, 0, 0, 0.06)',
  fontSize: '0.72rem',
  fontWeight: 600,
  color: theme.palette.mode === 'dark' ? '#e0e0e0' : '#555',
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
  onCardClick = null,
  cardHints = null,
  clickable = false,
  playableSet = null,
  selectedCardKey = null,
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
      const isPlayable = !playableSet || playableSet.has(cardKey)
      const canClick = clickable && onCardClick && isPlayable
      const hint = cardHints?.[cardKey]
      const isSelected = selectedCardKey === cardKey
      const el = (
        <Box
          component="span"
          key={i}
          onClick={canClick ? () => onCardClick(suitSymbol, rank) : undefined}
          sx={{
            textDecoration: isPlayed ? 'line-through' : 'none',
            opacity: isPlayed ? 0.45 : (clickable && !isPlayable ? 0.45 : 1),
            color: color,
            fontWeight: 600,
            letterSpacing: '0.01em',
            cursor: canClick ? 'pointer' : undefined,
            transition: 'transform 0.1s, textShadow 0.1s',
            textShadow: isPlayable && clickable ? '0 0 4px currentColor' : 'none',
            outline: isSelected ? '2px solid' : 'none',
            outlineColor: isSelected ? 'primary.main' : undefined,
            outlineOffset: '2px',
            borderRadius: '2px',
            px: '2px',
            transform: isSelected ? 'scale(1.2)' : undefined,
            '&:hover': canClick ? {
              transform: isSelected ? 'scale(1.3)' : 'scale(1.3)',
              textShadow: '0 0 8px currentColor',
            } : {},
          }}
        >
          {rank}
        </Box>
      )
      if (hint) {
        return (
          <Tooltip key={i} title={hint} arrow placement="top" enterDelay={200}>
            {el}
          </Tooltip>
        )
      }
      return el
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
                <SuitSymbol sx={{ color }}>{symbol}</SuitSymbol>
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
