import React, { useMemo, useRef, useEffect, useState } from 'react'
import { Box, Typography, useTheme } from '@mui/material'
import { styled } from '@mui/material/styles'

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme }) => ({
  borderRadius: 0,
  padding: 0,
  width: '100%',
  height: '100%',
  fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
  fontWeight: 600,
  transition: 'all 0.25s ease',
  color: theme.palette.mode === 'dark' ? '#f5f5f5' : '#1a1a1a',
}));

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

// ── 牌面颜色 ──
const SUIT_COLORS = { '♠': '#1a1a2e', '♥': '#d32f2f', '♦': '#d32f2f', '♣': '#1a1a2e' }
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
  const fontSize = Math.max(8, cardW * 0.32)
  const smallFont = Math.max(5.5, cardW * 0.18)

  const isVertical = orientation === 'vertical'
  const hoverTransform = 'translateY(-14px)'

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
        opacity: isPlayed ? 0.45 : (!isPlayable ? 0.45 : 1),
        filter: isPlayed ? 'grayscale(0.6)' : (!isPlayable ? 'grayscale(0.3)' : 'none'),
        transform: isSelected ? hoverTransform : 'none',
        transformOrigin: 'center center',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease, border 0.15s ease',
        zIndex: isSelected ? 999 : 1,
        '&:hover': isPlayable ? {
          transform: hoverTransform,
          boxShadow: '0 6px 18px rgba(0,0,0,0.22), 0 2px 4px rgba(0,0,0,0.1)',
          zIndex: 999,
        } : {},
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

      {/* DD hint 小标签 */}
      {hint && (
        <Box sx={{
          position: 'absolute', bottom: -3, left: '50%', transform: 'translateX(-50%)',
          bgcolor: hint === '=' || hint.startsWith('+') ? '#c8e6c9' : '#ffcdd2',
          color: hint === '=' || hint.startsWith('+') ? '#2e7d32' : '#c62828',
          fontSize: `${Math.max(5, cardW * 0.15)}rem`,
          fontWeight: 800,
          px: 0.2, borderRadius: 2,
          lineHeight: 1.1,
          whiteSpace: 'nowrap',
          zIndex: 2,
          border: '1px solid rgba(0,0,0,0.1)',
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
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const containerRef = useRef(null)
  const [containerSize, setContainerSize] = useState(0)

  useEffect(() => {
    if (containerRef.current) {
      const obs = new ResizeObserver(entries => {
        for (const entry of entries) {
          // 横向用宽度，纵向用高度作为可用空间
          if (orientation === 'vertical') {
            setContainerSize(entry.contentRect.height)
          } else {
            setContainerSize(entry.contentRect.width)
          }
        }
      })
      obs.observe(containerRef.current)
      return () => obs.disconnect()
    }
  }, [orientation])

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

    const isVertical = orientation === 'vertical'
    const stepUnit = cardWidth

    const cardHeight = cardWidth * CARD_ASPECT
    const totalLength = isVertical
      ? cardWidth + (allCards.length - 1) * cardWidth * (1 - overlapRatio)
      : totalFanLength

    // 纵向模式下水平对齐：西家靠左，东家靠右
    const alignItems = isVertical
      ? (popDirection === 'left' ? 'flex-end' : 'flex-start')
      : 'center'

    return (
      <Box ref={containerRef} sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems,
        flexDirection: isVertical ? 'column' : 'row',
        width: '100%',
        height: '100%',
        position: 'relative',
        overflow: 'visible',
      }}>
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

            // 弹出方向：都向中心
            // 西家(right)：向右 → translateX(14px)
            // 东家(left)：向左 → translateX(-14px)
            const hoverDx = popDirection === 'left' ? -14 : 14

            const rotateDeg = popDirection === 'left' ? -90 : 90

            return (
              <Box
                key={card.cardKey}
                sx={{
                  position: 'absolute',
                  left: isVertical ? '50%' : offset,
                  top: isVertical ? offset : '50%',
                  transform: isVertical
                    ? `translateX(-50%) rotate(${rotateDeg}deg)`
                    : 'translateY(-50%)',
                  transformOrigin: 'center center',
                  zIndex: zIdx,
                  '&:hover': isPlayable ? {
                    transform: isVertical
                      ? `translateX(-50%) rotate(${rotateDeg}deg) translateX(${hoverDx}px)`
                      : `translateY(-50%) translateY(-14px)`,
                    zIndex: 999,
                  } : {},
                  transition: 'transform 0.15s ease',
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
                  hint={hint}
                  orientation={orientation}
                  popDirection={popDirection}
                />
              </Box>
            )
          })}
        </Box>
      </Box>
    )
  }

  return (
    <HandCard isActive={isActive} isHuman={isHuman} isPartner={isPartner}>
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
    </HandCard>
  );
}

export default HandDisplay;
