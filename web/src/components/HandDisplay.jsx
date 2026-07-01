import React, { useMemo, useRef, useEffect, useState } from 'react'
import { Box, Typography, useTheme } from '@mui/material'
import { styled } from '@mui/material/styles'

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme }) => ({
  borderRadius: 0,
  padding: 0,
  width: '100%',
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

// ── 自适应参数 ──
const MAX_CARD_WIDTH = 72
const MIN_CARD_WIDTH = 46
const CARD_ASPECT = 1.42   // 宽:高 ≈ 1:1.42 (桥牌比例)
const BASE_OVERLAP = 0.25  // 基础重叠比例

/** 单张扑克牌面 */
function PlayingCard({
  suit, rank, color, size, fanAngle, isSelected, isPlayable, isPlayed, onClick, hint, style,
}) {
  const cardW = size
  const cardH = size * CARD_ASPECT
  const fontSize = Math.max(8, cardW * 0.32)
  const smallFont = Math.max(5.5, cardW * 0.18)

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
        transform: isSelected ? 'translateY(-6px)' : 'none',
        transformOrigin: 'center center',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease, border 0.15s ease',
        zIndex: isSelected ? 10 : 1,
        '&:hover': isPlayable ? {
          transform: 'translateY(-8px)',
          boxShadow: '0 6px 18px rgba(0,0,0,0.22), 0 2px 4px rgba(0,0,0,0.1)',
          zIndex: 10,
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
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const containerRef = useRef(null)
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    if (containerRef.current) {
      const obs = new ResizeObserver(entries => {
        for (const entry of entries) {
          setContainerWidth(entry.contentRect.width)
        }
      })
      obs.observe(containerRef.current)
      return () => obs.disconnect()
    }
  }, [])

  const hasCards = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs)

  // 将所有花色牌展平为单张牌数组（按花色顺序）
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

  // 自适应牌宽和重叠比例
  const { cardWidth, overlapRatio } = useMemo(() => {
    const count = allCards.length
    if (count === 0) return { cardWidth: MAX_CARD_WIDTH, overlapRatio: BASE_OVERLAP }
    const availW = Math.max(60, (containerWidth || 160) - 16) // padding
    const overlap = count > 10 ? 0.50 : count > 6 ? 0.38 : count > 3 ? 0.22 : 0.08
    const idealW = availW / (1 + (count - 1) * (1 - overlap))
    const w = Math.min(MAX_CARD_WIDTH, Math.max(MIN_CARD_WIDTH, idealW))
    return { cardWidth: w, overlapRatio: overlap }
  }, [allCards.length, containerWidth])

  // 牌面角度（不作扇形旋转，全部为0）
  const fanAngles = useMemo(() => allCards.map(() => 0), [allCards])

  // 总牌面宽度（含重叠）
  const totalFanWidth = useMemo(() => {
    if (allCards.length === 0) return 0
    return cardWidth + (allCards.length - 1) * cardWidth * (1 - overlapRatio)
  }, [allCards.length, cardWidth, overlapRatio])

  const renderCards = () => {
    if (allCards.length === 0) return null

    return (
      <Box ref={containerRef} sx={{
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'flex-end',
        width: '100%',
        height: cardWidth * CARD_ASPECT,
        pt: 0, pb: 0,
        position: 'relative',
      }}>
        <Box sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-end',
          position: 'relative',
          width: totalFanWidth,
          height: '100%',
          mx: 'auto',
        }}>
          {allCards.map((card, i) => {
            const isPlayed = playedCards && playedCards.has(card.cardKey)
            const isPlayable = !playableSet || playableSet.has(card.cardKey)
            const isSelected = selectedCardKey === card.cardKey
            const hint = cardHints?.[card.cardKey]
            const color = SUIT_COLORS[card.suit]

            // 每张牌向左重叠
            const offsetLeft = i * cardWidth * (1 - overlapRatio)

            return (
              <Box
                key={card.cardKey}
                sx={{
                  position: 'absolute',
                  left: offsetLeft,
                  bottom: 0,
                  zIndex: isSelected ? 10 : i + 1,
                }}
              >
                <PlayingCard
                  suit={card.suit}
                  rank={card.rank}
                  color={color}
                  size={cardWidth}
                  fanAngle={fanAngles[i]}
                  isSelected={isSelected}
                  isPlayable={clickable ? isPlayable : true}
                  isPlayed={!!isPlayed}
                  onClick={clickable && onCardClick ? () => onCardClick(card.suit, card.rank) : undefined}
                  hint={hint}
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
