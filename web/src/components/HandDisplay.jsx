import React, { useMemo } from 'react'
import { Box, Typography, useTheme } from '@mui/material'
import { styled } from '@mui/material/styles'

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 700,
  marginBottom: '4px',
  color: theme.palette.mode === 'dark' ? '#f0f0f0' : '#333',
  fontSize: '0.78rem',
  letterSpacing: '0.02em',
}));

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

// ── 牌面颜色（♥红、♦紫，高对比区分两种红色花色）──
const SUIT_COLORS = { '♠': '#1a1a2e', '♥': '#d32f2f', '♦': '#7c3aed', '♣': '#1a1a2e' }
const SUIT_SYMBOLS = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }
const SUIT_ORDER = ['spades', 'hearts', 'diamonds', 'clubs']

// ── 固定牌宽参数 ──
const FIXED_CARD_WIDTH = 65  // 固定牌宽
const CARD_ASPECT = 1.42   // 宽:高 ≈ 1:1.42 (桥牌比例)
const FIXED_OVERLAP = 0.65  // 固定重叠比例

/** 单张扑克牌面 */
function PlayingCard({
  suit, rank, color, size, isSelected, isPlayable, isPlayed, onClick, hint, style,
  orientation = 'horizontal',
  popDirection = 'auto',
  disableHover = false,
}) {
  // 统一比例：牌宽=size，牌高=size*1.42（正常竖向扑克牌）
  const cardW = size
  const cardH = size * CARD_ASPECT
  const fontSize = Math.max(8, cardW * 0.40)
  const smallFont = Math.max(5.5, cardW * 0.22)

  const isVertical = orientation === 'vertical'
  const hoverTransform = 'translateY(-15px)'

  return (
    <Box
      onClick={isPlayable && onClick ? onClick : undefined}
      sx={{
        width: cardW,
        height: cardH,
        flexShrink: 0,
        position: 'relative',
        bgcolor: isPlayed ? '#d0d0d0' : '#fcfcfc',
        borderRadius: `${Math.max(2, cardW * 0.1)}px`,
        border: isSelected
          ? `2px solid #ffc107`
          : isPlayed
            ? '1px solid #bbb'
            : '1px solid rgba(0,0,0,0.12)',
        boxShadow: isSelected
          ? `0 4px 14px rgba(255,193,7,0.5), 0 1px 3px rgba(0,0,0,0.15)`
          : isPlayed
            ? '0 1px 2px rgba(0,0,0,0.06)'
            : '0 2px 5px rgba(0,0,0,0.14), 0 1px 2px rgba(0,0,0,0.06)',
        cursor: isPlayable ? 'pointer' : 'default',
        opacity: 1,
        filter: isPlayed ? 'grayscale(1)' : 'none',
        transform: 'none',
        transformOrigin: 'center center',
        ...style,
      }}
    >
      {/* 左上角 rank+suit */}
      <Box sx={{
        position: 'absolute', top: 1, left: Math.max(1, cardW * 0.04),
        display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: 1,
      }}>
        <Typography sx={{ fontSize: smallFont, fontWeight: 700, color, lineHeight: 1 }}>{rank}</Typography>
        <Typography sx={{ fontSize: Math.max(4, smallFont * 0.75), color, lineHeight: 1 }}>{suit}</Typography>
      </Box>

      {/* 中央大号花色 */}
      <Box sx={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
      }}>
        <Typography sx={{ fontSize, color, lineHeight: 1, fontWeight: 500 }}>{suit}</Typography>
      </Box>

      {/* 右下角倒置 rank+suit */}
      <Box sx={{
        position: 'absolute', bottom: 1, right: Math.max(1, cardW * 0.04),
        display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: 1,
        transform: 'rotate(180deg)',
      }}>
        <Typography sx={{ fontSize: smallFont, fontWeight: 700, color, lineHeight: 1 }}>{rank}</Typography>
        <Typography sx={{ fontSize: Math.max(4, smallFont * 0.75), color, lineHeight: 1 }}>{suit}</Typography>
      </Box>

      {/* DD hint 小标签：统一放牌面本地左下角（rank+suit 在左上角，对侧边缘；四家旋转后均落在可见 peek 内） */}
      {hint && (
        <Box sx={{
          position: 'absolute',
          bottom: 2, left: 2,
          bgcolor: hint === '=' || hint.startsWith('+') ? '#c8e6c9' : '#ffcdd2',
          color: hint === '=' || hint.startsWith('+') ? '#2e7d32' : '#c62828',
          fontSize: `${Math.max(8, cardW * 0.14)}px`,
          fontWeight: 800,
          px: 0.3, borderRadius: 2,
          lineHeight: 1.1,
          whiteSpace: 'nowrap',
          zIndex: 4,
          border: '1px solid rgba(0,0,0,0.15)',
        }}>
          {hint}
        </Box>
      )}
    </Box>
  )
}

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
  orientation = 'horizontal', // 'horizontal' | 'vertical'
  popDirection = 'auto', // 'auto' | 'left' | 'right' 纵向时的弹出方向
  enableHover = false, // 是否启用悬停弹出效果
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const isVertical = orientation === 'vertical'
  const alignItems = isVertical
    ? (popDirection === 'left' ? 'flex-end' : 'flex-start')
    : 'center'

  const hasCards = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs)

  // 将所有花色牌展平为单张牌数组（按花色顺序 S→H→D→C）
  const allCards = useMemo(() => {
    if (!hand) return []
    const cards = []
    for (const suitName of SUIT_ORDER) {
      const suitStr = hand[suitName]
      const suitSymbol = SUIT_SYMBOLS[suitName]
      if (suitStr && suitStr !== '-') {
        for (const rank of suitStr.split('')) {
          cards.push({ suit: suitSymbol, rank, cardKey: suitSymbol + rank, suitName })
        }
      }
    }
    return cards
  }, [hand])

  // 固定牌宽和重叠比例
  const { cardWidth, overlapRatio } = useMemo(() => {
    return { cardWidth: FIXED_CARD_WIDTH, overlapRatio: FIXED_OVERLAP }
  }, [])

  // 总牌面长度（含重叠）- 沿主轴方向
  const totalFanLength = useMemo(() => {
    if (allCards.length === 0) return 0
    return cardWidth + (allCards.length - 1) * cardWidth * (1 - overlapRatio)
  }, [allCards.length, cardWidth, overlapRatio])

  const renderCards = () => {
    if (allCards.length === 0) return null

    const stepUnit = cardWidth

    const cardHeight = cardWidth * CARD_ASPECT
    const totalLength = isVertical
      ? cardWidth + (allCards.length - 1) * cardWidth * (1 - overlapRatio)
      : totalFanLength

    return (
      <Box sx={{
        display: 'flex',
        flexDirection: isVertical ? 'column' : 'row',
        position: 'relative',
        width: isVertical ? cardHeight : totalFanLength,
        height: isVertical ? totalLength : cardHeight,
        overflow: 'visible',
        flexShrink: 0,
      }}>
          {allCards.map((card, i) => {
            const isPlayed = playedCards && playedCards.has(card.cardKey)
            const isPlayable = !playableSet || playableSet.has(card.cardKey)
            const isSelected = selectedCardKey === card.cardKey
            const hint = cardHints?.[card.cardKey]
            const color = SUIT_COLORS[card.suit]

            const offset = i * stepUnit * (1 - overlapRatio)
            const total = allCards.length
            // 西家(right)：底下的牌覆盖上边的 → zIndex = i + 1
            // 东家(left)：上边的牌覆盖底下的 → zIndex = total - i
            const zIdx = isVertical && popDirection === 'left'
              ? (isSelected ? 999 : total - i)
              : (isSelected ? 999 : i + 1)

            // 弹出方向：都向中心 15px
            const hoverDx = popDirection === 'left' ? -15 : 15

            const rotateDeg = popDirection === 'left' ? -90 : 90

            const canHover = enableHover && isPlayable
            const showHint = enableHover && hint && isPlayable
            // 旋转后牌视觉宽度 = cardHeight，外层宽度 = cardWidth
            // hint距视觉牌边缘的偏移 = (cardHeight - cardWidth) / 2 + 间距
            const hintOffset = cardWidth * (CARD_ASPECT - 1) / 2 + 6
            return (
              <Box
                key={card.cardKey}
                sx={{
                  position: 'absolute',
                  left: isVertical ? '50%' : offset,
                  top: isVertical ? offset - (cardHeight - cardWidth) / 2 : 0,
                  transform: isVertical
                    ? 'translateX(-50%)'
                    : 'none',
                  zIndex: zIdx,
                }}
              >
                <Box
                  sx={{
                    transform: isVertical ? `rotate(${rotateDeg}deg)` : 'none',
                    transition: 'transform 0.15s ease',
                    '&:hover': canHover ? {
                      transform: isVertical
                        ? `translateX(${hoverDx}px) rotate(${rotateDeg}deg)`
                        : 'translateY(-15px)',
                    } : {},
                  }}
                >
                  <PlayingCard
                    suit={card.suit}
                    rank={card.rank}
                    color={color}
                    size={cardWidth}
                    isSelected={isSelected}
                    isPlayable={clickable ? isPlayable : true}
                    isPlayed={!!isPlayed}
                    onClick={clickable && onCardClick ? () => onCardClick(card.suit, card.rank) : undefined}
                    orientation={orientation}
                    popDirection={popDirection}
                  />
                  {/* DD hint 标签 - 牌面本地左下角（rank+suit 在左上角，对侧边缘；随牌旋转） */}
                  {showHint && (
                    <Box sx={{
                      position: 'absolute',
                      bottom: 2, left: 2,
                      color: hint === '=' || hint.startsWith('+') ? '#2e7d32' : '#c62828',
                      fontSize: `${Math.max(7, cardWidth * 0.16)}px`,
                      fontWeight: 800,
                      lineHeight: 1,
                      whiteSpace: 'nowrap',
                      zIndex: 10,
                      pointerEvents: 'none',
                      textShadow: '0 0 2px #fff, 0 0 2px #fff, 0 1px 1px rgba(0,0,0,0.3)',
                    }}>
                      {hint}
                    </Box>
                  )}
                </Box>
              </Box>
            )
          })}
        </Box>
    )
  }

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'flex-start',
      alignItems,
      width: 'auto',
      height: 'auto',
      overflow: 'visible',
      p: 0, m: 0,
      borderRadius: 0,
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
      fontWeight: 600,
      transition: 'all 0.25s ease',
      color: isDark ? '#f5f5f5' : '#1a1a1a',
    }}>
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
        renderCards()
      ) : (
        <HiddenHand>
          <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.8rem' }}>
            {hasCards ? '[隐藏]' : '[待输入]'}
          </Typography>
        </HiddenHand>
      )}
    </Box>
  );
}

export default HandDisplay;
