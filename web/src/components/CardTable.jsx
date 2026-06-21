import React, { useState, useMemo, useEffect } from 'react';
import { Box, Button, Chip, CircularProgress, TextField, ToggleButton, ToggleButtonGroup, Typography, IconButton, Tooltip, useTheme, useMediaQuery, alpha } from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import BorderColorIcon from '@mui/icons-material/BorderColor'
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted'

import GridOnIcon from '@mui/icons-material/GridOn'
import HandDisplay from './HandDisplay';
import { getSuitColor } from '../constants/suits';
import DoubleDummyTable from './DoubleDummyTable';
import { isHumanPosition, hasAnyHuman, getHumanPositions, BRIDGE_POSITIONS } from '../utils/position';
import { colorSchemes } from '../theme/colorSchemes';

function CardTable({
  hands,
  currentBidder,
  dealer,
  gameMode,
  showPartnerHand,
  showOpponentHands,
  getPartnerPosition,
  renderBiddingTable,
  checkBiddingComplete,
  outputFormats,
  outputFormatsLoading,
  handleAnalyzeContract,
  analyzeLoading,
  currentBiddingPosition,
  showDoubleDummy,
  doubleDummyResult,
  doubleDummyLoading,
  biddingTotalTime,
  positionRoles,
  onPositionRoleChange,
  onDealerChange,
  onClearAllHands,
  onSimulatedReset,
  setHands,
  biddingStarted,
  stopBidding,
  declarer,
  playState,
  showPlayPanel,
  lastCompletedTrick,
  isPlayPaused,
  playInitiated,
  aiLoading,
  showPlayedCards = false,
  playCenterView = 'play',
  onEditHands,
  onEditBidding,
  aiBiddingHistory = [],
  onPlayCardClick,
  onSetPlayHand,
  readonlyMode = false,
  mode,
  imageOpeningLead,
  // 叫牌控件相关
  addBid,
  isBiddingCompleteFn,
  onHandCardClick,
  cardHints,
  biddingSequence,
  onManualPlay,
  reviewCursor,
  reviewTrick,
}) {
  const [handInputs, setHandInputs] = useState({
    '南': '',
    '北': '',
    '东': '',
    '西': ''
  })
  const [inputErrors, setInputErrors] = useState({
    '南': '',
    '北': '',
    '东': '',
    '西': ''
  })
  const [selectedBidLevel, setSelectedBidLevel] = useState(null)
  const [mobileSelectedCard, setMobileSelectedCard] = useState(null) // 手机端双击出牌
  const [manualCardInput, setManualCardInput] = useState({}) // {position: string} 手动出牌输入
  // 出牌人变化时清除手机端选中
  useEffect(() => {
    setMobileSelectedCard(null)
  }, [playState?.current_player])

  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  const isDark = theme.palette.mode === 'dark'
  const iconBtnStyle = {
    bgcolor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.35)',
    backdropFilter: 'blur(8px)',
    color: 'white',
    border: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid rgba(255,255,255,0.3)',
    '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.55)' },
    transition: 'all 0.2s ease',
    width: 30, height: 30,
  }
  const textMuted = theme.palette.text.secondary
  const textPrimary = theme.palette.text.primary
  const handBoxSize = isMobile ? 'calc((100vw - 12px) * 0.42)' : 160
  const biddingTableWidth = isMobile ? 'calc((100vw - 12px) * 0.5)' : 160
  const centerBoxSize = isMobile ? 120 : 220

  if (!hands) return null;

  const north = hands['北'];
  const south = hands['南'];
  const east = hands['东'];
  const west = hands['西'];

  const defaultScheme = {
    ...colorSchemes.classicGreen,
    table: {
      ...colorSchemes.classicGreen.table,
      centerShadow: 'inset 0 2px 12px rgba(0,0,0,0.25), 0 4px 20px rgba(0,0,0,0.2)',
    },
  }

  const scheme = {
    ...defaultScheme,
    table: {
      ...defaultScheme.table,
      ...(isDark ? {
        background: 'radial-gradient(ellipse at center, #1a2f22 0%, #0d1f15 50%, #06120d 100%)',
        border: defaultScheme.table.border ?? 'none',
        centerBg: 'rgba(0, 0, 0, 0.28)',
        centerBackdrop: defaultScheme.table.centerBackdrop || 'blur(12px) saturate(140%)',
        centerBorder: defaultScheme.table.centerBorder || '1px solid rgba(255, 255, 255, 0.10)',
        centerShadow: defaultScheme.table.centerShadow || 'inset 0 2px 12px rgba(0,0,0,0.35), 0 4px 20px rgba(0,0,0,0.25)',
      } : {
        centerBackdrop: defaultScheme.table.centerBackdrop || 'blur(12px) saturate(140%)',
        centerBorder: defaultScheme.table.centerBorder || '1px solid rgba(255, 255, 255, 0.12)',
        centerShadow: defaultScheme.table.centerShadow || 'inset 0 2px 12px rgba(0,0,0,0.25), 0 4px 20px rgba(0,0,0,0.2)',
      }),
    },
  };

  const isAIPosition = (position) => {
    return positionRoles && positionRoles[position] === 'ai'
  }

  const hasHand = (position) => {
    const hand = hands[position]
    return hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs)
  }

  // 计算打牌阶段已出的牌（用于显示模式）
  // 缓存：一次遍历所有墩，避免每个 position 重复遍历
  const playedCardCache = useMemo(() => {
    if (!showPlayPanel || !playState) return null
    const playedCardsSet = new Set()
    const playedByPosition = { '北': [], '东': [], '南': [], '西': [] }
    for (const trick of (playState.tricks || [])) {
      for (const [pos, card] of (trick.cards || [])) {
        const key = card.suit + card.rank
        playedCardsSet.add(key)
        playedByPosition[pos].push({ suit: card.suit, rank: card.rank })
      }
    }
    for (const [pos, card] of (playState.current_trick?.cards || [])) {
      const key = card.suit + card.rank
      playedCardsSet.add(key)
      playedByPosition[pos].push({ suit: card.suit, rank: card.rank })
    }
    return { playedCardsSet, playedByPosition }
  }, [showPlayPanel, playState?.tricks, playState?.current_trick?.cards])

  const getPlayedCardsSet = () => {
    return playedCardCache?.playedCardsSet ?? null
  }

  // 计算当前可出的牌（跟花色规则）
  const playableCardSet = useMemo(() => {
    if (!showPlayPanel || !playState || playState.phase === 'complete') return null
    const cp = playState.current_player
    if (!cp) return null
    const hand = playState.hands?.[cp]
    if (!hand || hand.length === 0) return null
    const trickCards = playState.current_trick?.cards || []
    const ledSuit = trickCards.length > 0 ? trickCards[0][1]?.suit : null
    const set = new Set()
    for (const card of hand) {
      if (!ledSuit || card.suit === ledSuit) {
        set.add(card.suit + card.rank)
      }
    }
    // 如果没有可跟的花色，所有牌都可出
    if (set.size === 0) {
      for (const card of hand) set.add(card.suit + card.rank)
    }
    return set
  }, [showPlayPanel, playState?.current_player, playState?.current_trick?.cards?.length, playState?.hands])

  // 打牌阶段的手牌：隐藏模式下用剩余手牌，显示模式下用原始手牌+已出标记
  const getManualPlayedCards = (position) => {
    return playedCardCache?.playedByPosition[position] ?? []
  }

  const drawHandFromPlayedCards = (position, manualCards) => {
    const suitNames = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
    const newHand = { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
    const groups = { spades: [], hearts: [], diamonds: [], clubs: [] }
    for (const c of manualCards) {
      const sn = suitNames[c.suit]
      if (sn) groups[sn].push(c.rank)
    }
    const rankOrder = 'AKQJT98765432'
    for (const [suitName, ranks] of Object.entries(groups)) {
      ranks.sort((a, b) => rankOrder.indexOf(a) - rankOrder.indexOf(b))
      newHand[suitName] = ranks.join('')
    }
    return newHand
  }

  // 打牌阶段的手牌：隐藏模式下用剩余手牌，显示模式下用原始手牌+已出标记
  const getPlayHand = (position) => {
    if (!showPlayPanel || !playState) return hands[position]
    
    if (showPlayedCards) {
      const originalHand = hands[position]
      if (hasHand(position)) return originalHand
      const psHand = playState.hands?.[position]
      const manualCards = getManualPlayedCards(position)
      const allCards = []
      if (psHand) allCards.push(...psHand)
      if (manualCards.length > 0) allCards.push(...manualCards)
      if (allCards.length > 0) return drawHandFromPlayedCards(position, allCards)
      return originalHand
    }
    
    // 隐藏模式（默认）：用后端返回的剩余手牌，转为 HandDisplay 格式
    const remainingCards = playState.hands?.[position]
    if (!remainingCards) return hands[position]
    
    const suitNames = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
    const rankOrder = 'AKQJT98765432'
    const newHand = { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
    // 按花色分组，每个花色内按从大到小排序
    const suitGroups = { spades: [], hearts: [], diamonds: [], clubs: [] }
    for (const card of remainingCards) {
      const suitName = suitNames[card.suit]
      if (suitName) {
        suitGroups[suitName].push(card.rank)
      }
    }
    for (const [suitName, ranks] of Object.entries(suitGroups)) {
      ranks.sort((a, b) => rankOrder.indexOf(a) - rankOrder.indexOf(b))
      newHand[suitName] = ranks.join('')
    }
    return newHand
  }

  const parseHandInput = (input) => {
    const suits = input.trim().split(/\s+/)
    if (suits.length !== 4) {
      return { valid: false, error: '请输入4个花色，用空格分隔' }
    }

    const validCards = /^[AKQJTakqjt2-9\-]+$/
    for (const suit of suits) {
      if (suit !== '-' && !validCards.test(suit)) {
        return { valid: false, error: '包含无效字符' }
      }
    }

    // 张数校验：每手牌必须是13张
    const totalCards = suits.reduce((sum, s) => sum + (s === '-' ? 0 : s.length), 0)
    if (totalCards !== 13) {
      return { valid: false, error: `张数不对：${totalCards}张（需要13张）` }
    }

    const calculateHCP = (cards) => {
      let hcp = 0
      for (const card of cards.toUpperCase()) {
        if (card === 'A') hcp += 4
        else if (card === 'K') hcp += 3
        else if (card === 'Q') hcp += 2
        else if (card === 'J') hcp += 1
      }
      return hcp
    }

    const spades = suits[0] === '-' ? '' : suits[0].toUpperCase()
    const hearts = suits[1] === '-' ? '' : suits[1].toUpperCase()
    const diamonds = suits[2] === '-' ? '' : suits[2].toUpperCase()
    const clubs = suits[3] === '-' ? '' : suits[3].toUpperCase()

    // 重复牌校验：与已确认的其他位置手牌比对
    const allHandCards = new Map() // '♠A' -> position
    for (const [pos, hand] of Object.entries(hands || {})) {
      if (!hand || typeof hand !== 'object') continue
      for (const [suit, suitRanks] of Object.entries(hand)) {
        if (!suitRanks || suitRanks === '-' || typeof suitRanks !== 'string') continue
        const suitSymbol = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[suit] || suit
        for (const rank of suitRanks) {
          allHandCards.set(`${suitSymbol}${rank}`, pos)
        }
      }
    }
    const newCards = [
      ...(spades ? spades.split('').map(r => `♠${r}`) : []),
      ...(hearts ? hearts.split('').map(r => `♥${r}`) : []),
      ...(diamonds ? diamonds.split('').map(r => `♦${r}`) : []),
      ...(clubs ? clubs.split('').map(r => `♣${r}`) : []),
    ]
    for (const card of newCards) {
      if (allHandCards.has(card)) {
        return { valid: false, error: `${card} 已在${allHandCards.get(card)}家手牌中` }
      }
    }

    return {
      valid: true,
      hand: {
        spades,
        hearts,
        diamonds,
        clubs,
        hcp: calculateHCP(spades + hearts + diamonds + clubs)
      }
    }
  }

  const handleHandInputChange = (position, value) => {
    setHandInputs(prev => ({ ...prev, [position]: value }))
    setInputErrors(prev => ({ ...prev, [position]: '' }))
  }

  const handleHandInputSubmit = (position) => {
    const result = parseHandInput(handInputs[position])
    if (!result.valid) {
      setInputErrors(prev => ({ ...prev, [position]: result.error }))
      return
    }
    
    setHands(prev => ({
      ...prev,
      [position]: result.hand
    }))
    setHandInputs(prev => ({ ...prev, [position]: '' }))
  }

  const handleAIHandSubmit = (position) => {
    const result = parseHandInput(handInputs[position])
    if (!result.valid) {
      setInputErrors(prev => ({ ...prev, [position]: result.error }))
      return
    }
    onSetPlayHand?.(position, result.hand)
    setHandInputs(prev => ({ ...prev, [position]: '' }))
  }

  const shouldShowHandContent = (position) => {
    if (showPlayPanel && playState) {
      const dummy = playState.dummy
      const declarerPos = playState.contract?.declarer
      const playerRoles = playState.player_roles || positionRoles

      const role = (playerRoles && playerRoles[position]) || (positionRoles && positionRoles[position])

      // 人类自己的手牌始终可见
      if (role === 'human') return true

      // 全AI旁观：显示所有手牌（包括明手，不等首攻）
      if (!hasAnyHuman(positionRoles)) return true

      // 有人类参与：明手首攻后才显示
      if (position === dummy) return playState.phase !== 'lead'

      // 有人类参与：不全4家手牌时（模拟实战/部分输入），AI有手牌就显示
      const totalWithHands = ['南','北','东','西'].filter(p => hasHand(p)).length
      if (role !== 'human' && totalWithHands < 4 && hasHand(position)) return true

      // 全4家手牌（正常发牌）：AI手牌默认不显示，由checkbox控制
      const declRole = (playerRoles && playerRoles[declarerPos]) || (positionRoles && positionRoles[declarerPos])
      if (declRole === 'ai') {
        // 庄家是AI（人类是防守方）：AI庄家→对方，AI防守队友→队友
        if (position === declarerPos) return showOpponentHands
        return showPartnerHand
      } else {
        // 庄家是人类（AI都是防守方）→ 对方
        return showOpponentHands
      }
    }

    // 叫牌阶段
    if (gameMode === 'pair') {
      const partnerPos = getPartnerPosition(dealer)
      if (position === dealer) return true
      if (position === partnerPos) return showPartnerHand
      return showOpponentHands
    }
    // 四人模式
    if (!hasAnyHuman(positionRoles)) return true             // 全AI旁观：显示所有手牌
    if (isHumanPosition(positionRoles, position)) return true // 人类：有牌显示/无牌"未知"
    // 3H+1AI 模拟实战或4H：AI位置始终显示
    if (getHumanPositions(positionRoles).length >= 3) return true
    // 1H+3AI 练习模式：对面为队友，两侧为对方
    const humanPos = getHumanPositions(positionRoles)[0]
    const partnerPos = getPartnerPosition(humanPos)
    if (position === partnerPos) return showPartnerHand
    return showOpponentHands
  };

  // 打牌阶段的叫牌过程表格（带tooltip显示叫牌含义）
  const renderPlayBiddingTable = () => {
    const positions = BRIDGE_POSITIONS

    // 从 aiBiddingHistory 提取序列
    let seq = []
    if (aiBiddingHistory && aiBiddingHistory.length > 0) {
      seq = aiBiddingHistory.map(r => ({ position: r.position, bid: r.result?.bid || 'pass', meaning: r.result?.meaning || '' }))
    }

    if (seq.length === 0) {
      return renderBiddingTable ? renderBiddingTable() : (
        <div style={{ color: textMuted, fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
          无叫牌记录
        </div>
      )
    }

    const rows = []
    let currentRow = Array(4).fill(null)
    let currentRowInfo = Array(4).fill(null)

    seq.forEach((bid) => {
      const posIndex = positions.indexOf(bid.position)
      currentRow[posIndex] = bid.bid
      currentRowInfo[posIndex] = bid.meaning

      if (posIndex === 3) {
        rows.push({ bids: [...currentRow], info: [...currentRowInfo] })
        currentRow = Array(4).fill(null)
        currentRowInfo = Array(4).fill(null)
      }
    })

    if (currentRow.some(cell => cell !== null)) {
      rows.push({ bids: [...currentRow], info: [...currentRowInfo] })
    }

    return (
      <Box sx={{
        width: '100%',
        fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
        fontSize: '0.9rem',
      }}>
        <Box sx={{
          display: 'flex',
          justifyContent: 'space-around',
          borderBottom: `2px solid ${theme.palette.text.primary}`,
          paddingBottom: 0.5,
          marginBottom: 0.5,
          fontWeight: 'bold',
          color: textPrimary,
          position: 'sticky',
          top: 0,
          zIndex: 2,
        }}>
          {positions.map(pos => (
            <Box key={pos} component="span" sx={{ flex: 1, textAlign: 'center', minWidth: 50, color: pos === dealer ? theme.palette.error.main : 'inherit' }}>
              {pos}
            </Box>
          ))}
        </Box>
        {rows.map((row, rowIndex) => (
          <Box key={rowIndex} sx={{
            display: 'flex',
            justifyContent: 'space-around',
            padding: '4px 0',
            borderBottom: `1px solid ${theme.palette.divider}`,
            '&:last-child': { borderBottom: 'none' },
          }}>
            {positions.map((pos, colIndex) => {
              const bid = row.bids[colIndex]
              const meaning = row.info[colIndex]
              if (!bid) {
                return <Box key={colIndex} component="span" sx={{ flex: 1, textAlign: 'center', minWidth: 50 }} />
              }
              const displayText = bid === 'pass' ? 'P' : bid
              const cellEl = (
                <Box
                  component="span"
                  sx={{
                    flex: 1,
                    textAlign: 'center',
                    minWidth: 50,
                    fontWeight: 500,
                    color: textPrimary,
                    backgroundColor: alpha(theme.palette.primary.main, 0.08),
                    borderRadius: 1,
                    cursor: meaning ? 'pointer' : 'default',
                    padding: '2px 0',
                  }}
                >
                  {displayText}
                </Box>
              )
              if (meaning) {
                return (
                  <Tooltip key={colIndex} title={meaning} arrow placement="top">
                    {cellEl}
                  </Tooltip>
                )
              }
              return cellEl
            })}
          </Box>
        ))}
      </Box>
    )
  }

  // 中心区域内容渲染（桌面版和手机版共用）
  const renderCenterContent = () => {
    if (showPlayPanel && playState) {
      if (playCenterView === 'bidding') {
        return renderPlayBiddingTable()
      }
      if (playCenterView === 'result' || showDoubleDummy) {
        return doubleDummyLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', width: '100%' }}>
            <CircularProgress size={24} />
          </Box>
        ) : doubleDummyResult ? (
          <DoubleDummyTable tableData={doubleDummyResult} />
        ) : (
          <div style={{ color: textMuted, fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
            无分析结果
          </div>
        )
      }
      return renderCurrentTrick()
    }
    return showDoubleDummy ? (
      doubleDummyLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', width: '100%' }}>
          <CircularProgress size={24} />
        </Box>
      ) : doubleDummyResult ? (
        <DoubleDummyTable tableData={doubleDummyResult} />
      ) : (
        <div style={{ color: textMuted, fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
          无分析结果
        </div>
      )
    ) : renderBiddingTable ? renderBiddingTable() : (
      <div style={{ color: textMuted, fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
        等待叫牌...
      </div>
    );
  };

  const renderCurrentTrick = () => {
    if (!playState) return null

    const { current_trick, current_player, phase } = playState
    const isComplete = phase === 'complete'
    const isReview = reviewCursor != null

    // 复盘模式：显示 reviewTrick；否则优先当前墩，再 lastCompletedTrick
    const displayTrick = isReview && reviewTrick
      ? reviewTrick
      : (current_trick?.cards && current_trick.cards.length > 0)
        ? current_trick
        : lastCompletedTrick ? lastCompletedTrick : current_trick
    
    const getCardAtPosition = (position) => {
      if (!displayTrick?.cards) return null
      const cardEntry = displayTrick.cards.find(([pos]) => pos === position)
      return cardEntry ? cardEntry[1] : null
    }
    
    const getLastTrickWinner = () => {
      if (lastCompletedTrick) {
        return lastCompletedTrick?.winner
      }
      return null
    }
    
    const renderCard = (position) => {
      const card = getCardAtPosition(position)
      const positionLabels = { '北': 'N', '东': 'E', '南': 'S', '西': 'W' }
      const canClick = onPlayCardClick

      if (!card) {
        return (
          <Box sx={{
            width: 44,
            height: 60,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'rgba(255,255,255,0.06)',
            border: '1px dashed rgba(255,255,255,0.18)',
            borderRadius: '6px',
          }}>
            <Typography sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.7rem', fontWeight: 600 }}>
              {positionLabels[position]}
            </Typography>
          </Box>
        )
      }

      const color = getSuitColor(card.suit, isDark)

      return (
        <Box
          onClick={() => canClick && onPlayCardClick(position, card)}
          sx={{
            width: 44,
            height: 60,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: '#fbfbf8',
            border: '1px solid rgba(0,0,0,0.08)',
            borderRadius: '6px',
            boxShadow: '0 2px 6px rgba(0,0,0,0.22)',
            cursor: canClick ? 'pointer' : 'default',
            animation: 'cardIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)',
            '@keyframes cardIn': {
              '0%': { opacity: 0, transform: 'scale(0.7) translateY(-6px)' },
              '100%': { opacity: 1, transform: 'scale(1) translateY(0)' },
            },
            '&:hover': canClick ? { transform: 'scale(1.05) translateY(-2px)', boxShadow: '0 4px 10px rgba(0,0,0,0.28)' } : {},
          }}
        >
          <Typography sx={{ color, fontWeight: 'bold', fontSize: '1.1rem' }}>
            {card.suit}{card.rank}
          </Typography>
        </Box>
      )
    }

    return (
      <Box sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        width: '100%',
        gap: '6px',
      }}>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          {renderCard('北')}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '10px' }}>
          {renderCard('西')}
          <Box sx={{ width: 56, height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', borderRadius: '50%', bgcolor: 'rgba(0,0,0,0.2)' }}>
            {aiLoading ? (
              <CircularProgress size={22} sx={{ color: 'rgba(255,255,255,0.8)' }} />
            ) : isReview ? (
              <Typography sx={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#ffc107', textAlign: 'center' }}>
                第{reviewCursor + 1}墩
              </Typography>
            ) : (displayTrick?.cards?.length === 4 && getLastTrickWinner()) ? (
              <Typography sx={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#ffeb3b' }}>
                {getLastTrickWinner()}赢
              </Typography>
            ) : !isComplete && current_player ? (
              <Typography sx={{ fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.75)', textAlign: 'center' }}>
                {current_player}<br/>出牌
              </Typography>
            ) : null}
          </Box>
          {renderCard('东')}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          {renderCard('南')}
        </Box>
      </Box>
    )
  };

  const renderHandWithStatus = (hand, position, sxProps) => {
    const isCurrentlyBidding = currentBiddingPosition === position;
    const currentTurnPos = showPlayPanel ? playState?.current_player : currentBiddingPosition;
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = !readonlyMode && !showPlayPanel && isAI && !hasHandData && (!biddingStarted || stopBidding)
    const isHuman = positionRoles && positionRoles[position] === 'human'
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const showPlayHandInput = !readonlyMode && showPlayPanel && playState
      && (!playState.hands?.[position] || playState.hands[position].length === 0)
      && manualPlayedCount === 0
      && !(position === playState.dummy && playState.phase === 'lead')
      && (isAI || position === playState.dummy)
    const handKnownInPlay = showPlayPanel && playState?.hands?.[position]?.length > 0
    
    // 打牌阶段：根据模式选择手牌数据和已出牌标记
    const displayHand = getPlayHand(position)
    const playedCardsSet = (showPlayedCards && showPlayPanel && playState) ? getPlayedCardsSet() : null
    
    return (
      <Box sx={{ ...sxProps, position: 'relative' }}>
        {isCurrentlyBidding && (
          <Box sx={{
            position: 'absolute',
            top: 10,
            right: 8,
            zIndex: 100,
            bgcolor: 'rgba(0, 0, 0, 0.45)',
            backdropFilter: 'blur(6px)',
            borderRadius: '50%',
            p: 0.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(255,255,255,0.12)',
          }}>
            <CircularProgress size={14} sx={{ color: '#ffeb3b' }} />
          </Box>
        )}
        
        <Box sx={{
          bgcolor: isDark ? '#1e293b' : '#fbfbf8',
          borderRadius: 2,
          p: isMobile ? 0.5 : 1,
          width: handBoxSize,
          height: handBoxSize,
          flexShrink: 0,
          boxShadow: isDark
            ? '0 3px 10px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.25)'
            : '0 3px 10px rgba(0,0,0,0.15), 0 1px 2px rgba(0,0,0,0.08)',
          display: 'flex',
          flexDirection: 'column',
          border: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid rgba(0,0,0,0.06)',
          transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          ...(currentTurnPos === position && {
            boxShadow: `0 0 0 2px ${theme.palette.primary.main}, 0 4px 14px rgba(0,0,0,0.2)`,
          }),
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography 
              variant="subtitle2" 
              sx={{ 
                fontWeight: declarer === position ? 700 : 600, 
                fontSize: '0.85rem',
                color: declarer === position ? theme.palette.error.main : 'inherit',
                cursor: onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel && !readonlyMode ? 'pointer' : 'default',
                transition: 'color 0.2s',
                '&:hover': onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel && !readonlyMode ? { color: 'primary.main' } : {}
              }}
              onClick={() => onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel && !readonlyMode && onDealerChange(position)}
            >
              {position}家
              {dealer === position && ' *'}
              {hasHandData && hand && hand.hcp !== undefined && !showInput && ` (${hand.hcp})`}
            </Typography>
            {onPositionRoleChange && (
              <ToggleButton
                value="check"
                selected={positionRoles[position] === 'human'}
                disabled={
                  (showPlayPanel && playInitiated && (!isPlayPaused || aiLoading) && !((playState?.current_trick?.cards?.length || 0) === 0 && !aiLoading))
                  || readonlyMode
                  || (!showPlayPanel && biddingStarted && !hasHand(position))
                }
                onChange={() => {
                  onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')
                }}
                size="small"
                sx={{
                  height: 22,
                  px: 0.8,
                  py: 0,
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  borderRadius: 1,
                  minWidth: 36,
                  border: 'none',
                  bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.12)' : 'action.hover',
                  color: 'text.primary',
                  '&:hover': {
                    bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.2)' : 'action.selected',
                  },
                }}
              >
                {positionRoles[position] === 'human' ? '人类' : 'AI'}
              </ToggleButton>
            )}
          </Box>
          
          {/* 明手首攻前无手牌 → 显示未知 */}
          {showPlayPanel && playState && position === playState.dummy && playState.phase === 'lead' && !hasHand(position) ? (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.8rem' }}>[未知]</Typography>
            </Box>
          ) : showInput ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
              <TextField
                size="small"
                value={handInputs[position]}
                onChange={(e) => handleHandInputChange(position, e.target.value)}
                error={!!inputErrors[position]}
                helperText={inputErrors[position] || 'AKQJ T98 T87 654（13张，用 - 表示缺门）'}
                fullWidth
                multiline
                maxRows={2}
                sx={{ 
                  '& .MuiInputBase-input': { fontSize: '0.75rem', padding: '4px' },
                  '& .MuiFormHelperText-root': { fontSize: '0.6rem', margin: '2px 0 0 0' }
                }}
              />
              <Button 
                size="small" 
                variant="contained" 
                sx={{ mt: 0.5, fontSize: '0.7rem', py: 0.3 }}
                onClick={() => handleHandInputSubmit(position)}
                disabled={!handInputs[position].trim()}
              >
                确认
              </Button>
            </Box>
          ) : showPlayHandInput ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <TextField
                size="small"
                value={handInputs[position]}
                onChange={(e) => handleHandInputChange(position, e.target.value)}
                error={!!inputErrors[position]}
                helperText={inputErrors[position] || `输入${position}家手牌（13张，如 AKQJ T98 T87 654）`}
                fullWidth
                multiline
                maxRows={2}
                sx={{ 
                  '& .MuiInputBase-input': { fontSize: '0.75rem', padding: '4px' },
                  '& .MuiFormHelperText-root': { fontSize: '0.6rem', margin: '2px 0 0 0' }
                }}
              />
              <Button 
                size="small" 
                variant="contained" 
                sx={{ mt: 0.5, fontSize: '0.7rem', py: 0.3 }}
                onClick={() => handleAIHandSubmit(position)}
                disabled={!handInputs[position].trim()}
              >
                确认
              </Button>
            </Box>
          ) : isHuman && !hasHandData && !handKnownInPlay && manualPlayedCount === 0 ? (
            <Box sx={{ 
              flex: 1,
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              color: 'text.secondary'
            }}>
              <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>未知</Typography>
            </Box>
          ) : (
            <Box sx={{ flex: 1 }}>
              <HandDisplay
                hand={displayHand}
                position={position}
                isActive={showPlayPanel ? playState?.current_player === position : currentBidder === position}
                isHuman={isHuman}
                isDealer={dealer === position}
                isPartner={hasAnyHuman(positionRoles) && isHumanPosition(positionRoles, getPartnerPosition(position))}
                showContent={shouldShowHandContent(position)}
                hideTitle={true}
                playedCards={playedCardsSet}
                clickable={showPlayPanel && isHuman && playState?.current_player === position && onHandCardClick}
                onCardClick={isMobile ? (suit, rank) => {
                  const key = suit + rank
                  if (mobileSelectedCard === key) {
                    // 第二次点击：出牌
                    onHandCardClick(suit, rank)
                    setMobileSelectedCard(null)
                  } else {
                    // 第一次点击：选中
                    setMobileSelectedCard(key)
                  }
                } : onHandCardClick}
                playableSet={playableCardSet}
                selectedCardKey={isMobile ? mobileSelectedCard : null}
                cardHints={cardHints}
              />
            </Box>
          )}
        </Box>
      </Box>
    );
  };

  return (
    <Box className="card-table-container" sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isMobile ? 'stretch' : 'center',
      justifyContent: 'center',
      padding: isMobile ? 0.5 : 1,
      background: scheme.table.background,
      borderRadius: 2,
      boxShadow: 0,
      flex: 1,
      maxWidth: '100%',
      maxHeight: '100%',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 模拟实战清空按钮：任何阶段可见可点击（叫牌/打牌均可） */}
      {!readonlyMode && onSimulatedReset && gameMode !== 'pair' && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 10,
        }}>
          <Tooltip title={showPlayPanel ? '清空手牌，重新开始' : '模拟实战'} arrow slotProps={{
            tooltip: { sx: { bgcolor: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)', color: isDark ? '#1e293b' : '#fff' } },
            arrow: { sx: { color: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)' } },
          }}>
            <IconButton
              size="small"
              onClick={onSimulatedReset}
              sx={{
                bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : 'rgba(255, 255, 255, 0.9)',
                color: isDark ? '#e2e8f0' : undefined,
                '&:hover': { bgcolor: isDark ? 'rgba(30, 41, 59, 1)' : 'rgba(255, 255, 255, 1)' },
              }}
            >
              <DeleteSweepIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
      
      {checkBiddingComplete && checkBiddingComplete() && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}>
          {biddingTotalTime !== null && !showPlayPanel && (
            <Box sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'white',
              px: 1.5,
              py: 0.5,
              borderRadius: 1,
              fontSize: '0.85rem',
              fontWeight: 'medium',
            }}>
              ⏱ {Math.floor(biddingTotalTime / 60)}:{(biddingTotalTime % 60).toString().padStart(2, '0')}
            </Box>
          )}
          {!readonlyMode && onClearAllHands && !showPlayPanel && (
            <Tooltip title="清除牌局" arrow slotProps={{
              tooltip: { sx: { bgcolor: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)', color: isDark ? '#1e293b' : '#fff' } },
              arrow: { sx: { color: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)' } },
            }}>
              <IconButton
                size="small"
                onClick={onClearAllHands}
                sx={iconBtnStyle}
              >
                <DeleteSweepIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {!readonlyMode && onEditHands && !showPlayPanel && (
            <Tooltip title="修正手牌" arrow slotProps={{
              tooltip: { sx: { bgcolor: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)', color: isDark ? '#1e293b' : '#fff' } },
              arrow: { sx: { color: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)' } },
            }}>
              <IconButton
                size="small"
                onClick={onEditHands}
                sx={iconBtnStyle}
              >
                <BorderColorIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {!readonlyMode && onEditBidding && !showPlayPanel && (
            <Tooltip title="编辑叫牌" arrow slotProps={{
              tooltip: { sx: { bgcolor: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)', color: isDark ? '#1e293b' : '#fff' } },
              arrow: { sx: { color: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)' } },
            }}>
              <IconButton
                size="small"
                onClick={onEditBidding}
                sx={iconBtnStyle}
              >
                <FormatListBulletedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {handleAnalyzeContract && outputFormats && !showPlayPanel && (
            <Tooltip title="检验定约 (Deep Finesse)" arrow slotProps={{
              tooltip: { sx: { bgcolor: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)', color: isDark ? '#1e293b' : '#fff' } },
              arrow: { sx: { color: isDark ? '#e2e8f0' : 'rgba(0,0,0,0.8)' } },
            }}>
              <IconButton
                size="small"
                onClick={handleAnalyzeContract}
                disabled={analyzeLoading}
                sx={iconBtnStyle}
              >
                {analyzeLoading ? <CircularProgress size={16} sx={{ color: 'white' }} /> : <GridOnIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}
          {outputFormatsLoading && <CircularProgress size={20} sx={{ color: 'white' }} />}
        </Box>
      )}

      {/* 定约/庄家/首攻 — 绿色桌面顶部靠右 */}
      {showPlayPanel && playState?.contract && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 10,
          display: 'flex',
          gap: 0.5,
        }}>
          <Chip
            label={`${playState.contract.level || '?'}${playState.contract.suit || 'NT'}${playState.contract.redoubled ? 'XX' : playState.contract.doubled ? 'X' : ''}`}
            size="small"
            sx={{ fontSize: '0.7rem', bgcolor: 'rgba(255,255,255,0.92)', color: '#1565c0', fontWeight: 700 }}
          />
          <Chip
            label={`庄家: ${playState.contract.declarer || '?'}`}
            variant="outlined"
            size="small"
            sx={{ fontSize: '0.7rem', bgcolor: 'rgba(255,255,255,0.88)', color: '#333' }}
          />
          {imageOpeningLead && (
            <Chip
              label={`首攻: ${imageOpeningLead}`}
              size="small"
              sx={{ fontSize: '0.7rem', bgcolor: 'rgba(255,243,205,0.92)', color: '#e65100', fontWeight: 500 }}
            />
          )}
        </Box>
      )}

      {isMobile ? (
        <>
          <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
            {renderHandWithStatus(north, '北', { mb: '12px' })}
          </Box>
          
          <Box sx={{ display: 'flex', gap: '4px', width: '100%', mb: '12px', justifyContent: 'center' }}>
            {renderHandWithStatus(west, '西')}
            {renderHandWithStatus(east, '东')}
          </Box>
          
          <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
            {renderHandWithStatus(south, '南', { mb: '12px' })}
          </Box>
          
          <Box className="table-center" sx={{ width: '100%', display: 'flex', justifyContent: isMobile ? 'flex-start' : 'center' }}>
            <Box className="table-border" sx={{
              width: biddingTableWidth,
              minWidth: biddingTableWidth,
              flexShrink: 0,
              minHeight: 80,
              border: scheme.table.centerBorder,
              borderRadius: 2,
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'flex-start',
              background: scheme.table.centerBg,
              backdropFilter: scheme.table.centerBackdrop,
              WebkitBackdropFilter: scheme.table.centerBackdrop,
              boxShadow: scheme.table.centerShadow,
              padding: 1,
              overflowY: 'auto',
            }}>
              {renderCenterContent()}
            </Box>
          </Box>
        </>
      ) : (
        <>
          {renderHandWithStatus(north, '北', { mb: 0 })}

          <Box className="middle-row" sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            width: '100%',
            maxWidth: 800,
            gap: '8px',
          }}>
            {renderHandWithStatus(west, '西')}

            <Box className="table-center">
              <Box className="table-border" sx={{
                width: centerBoxSize,
                height: centerBoxSize,
                border: scheme.table.centerBorder,
                borderRadius: 2,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                background: scheme.table.centerBg,
                backdropFilter: scheme.table.centerBackdrop,
                WebkitBackdropFilter: scheme.table.centerBackdrop,
                boxShadow: scheme.table.centerShadow,
                padding: 1,
                overflowY: 'auto',
              }}>
              {renderCenterContent()}
              </Box>
            </Box>

            {renderHandWithStatus(east, '东')}
          </Box>

          {renderHandWithStatus(south, '南', { mt: 0 })}
        </>
      )}

      {/* 人类回合浮动叫牌面板（右下角） */}
      {!showPlayPanel && !showDoubleDummy && hasAnyHuman(positionRoles) && biddingStarted && (() => {
        const humanTurn = isHumanPosition(positionRoles, currentBidder)
        const biddingComplete = isBiddingCompleteFn ? isBiddingCompleteFn() : false
        if (!humanTurn || biddingComplete) return null
        const suits = ['C', 'D', 'H', 'S', 'NT']
        const suitOrder = { C: 0, D: 1, H: 2, S: 3, NT: 4 }
        // 找到最后一个实质性叫品，确定最低合法叫品
        const seq = biddingSequence || []
        const lastRealBid = [...seq].reverse().find(b => b.bid !== 'pass')
        let minLevel = 1, minSuitIdx = -1
        if (lastRealBid) {
          const re = /^(\d+)([CDHSNT]+)$/
          const m = lastRealBid.bid.match(re)
          if (m) {
            minLevel = parseInt(m[1])
            minSuitIdx = suitOrder[m[2]] ?? -1
          }
        }
        // 每个阶数是否可用
        const levelAvailable = (l) => {
          if (l > minLevel) return true
          if (l === minLevel && minSuitIdx < 4) return true // 同阶还有更高花色
          return false
        }
        // 每个花色在给定阶数下是否可用
        const suitAvailable = (l, s) => {
          if (l > minLevel) return true
          if (l === minLevel) return suitOrder[s] > minSuitIdx
          return false
        }
        const getBidColor = (bid, disabled) => {
          const d = theme.palette.mode === 'dark'
          const s = bid?.slice(-1)
          const dim = disabled ? (d ? 0.35 : 0.3) : 1
          if (d) {
            if (s === 'H' || s === 'D') return { c: `rgba(252,165,165,${dim})`, bg: `rgba(239,68,68,${0.22*dim})`, b: `rgba(239,68,68,${0.35*dim})` }
            if (s === 'S' || s === 'C') return { c: `rgba(203,213,225,${dim})`, bg: `rgba(148,163,184,${0.18*dim})`, b: `rgba(148,163,184,${0.28*dim})` }
            if (s === 'T') return { c: `rgba(196,181,253,${dim})`, bg: `rgba(139,92,246,${0.22*dim})`, b: `rgba(139,92,246,${0.35*dim})` }
            if (bid === 'X') return { c: `rgba(252,165,165,${dim})`, bg: `rgba(239,68,68,${0.22*dim})`, b: `rgba(239,68,68,${0.40*dim})` }
            if (bid === 'XX') return { c: `rgba(248,113,113,${dim})`, bg: `rgba(239,68,68,${0.26*dim})`, b: `rgba(239,68,68,${0.45*dim})` }
            if (bid === 'pass') return { c: `rgba(110,231,183,${dim})`, bg: `rgba(16,185,129,${0.18*dim})`, b: `rgba(16,185,129,${0.30*dim})` }
            return { c: `rgba(148,163,184,${dim})`, bg: `rgba(148,163,184,${0.12*dim})`, b: `rgba(148,163,184,${0.18*dim})` }
          }
          if (s === 'H' || s === 'D') return { c: `rgba(220,38,38,${dim})`, bg: `rgba(254,242,242,${dim})`, b: `rgba(252,165,165,${dim})` }
          if (s === 'S' || s === 'C') return { c: `rgba(30,41,59,${dim})`, bg: `rgba(241,245,249,${dim})`, b: `rgba(148,163,184,${dim})` }
          if (s === 'T') return { c: `rgba(124,58,237,${dim})`, bg: `rgba(245,243,255,${dim})`, b: `rgba(167,139,250,${dim})` }
          if (bid === 'X') return { c: `rgba(220,38,38,${dim})`, bg: `rgba(254,242,242,${dim})`, b: `rgba(252,165,165,${dim})` }
          if (bid === 'XX') return { c: `rgba(220,38,38,${dim})`, bg: `rgba(254,226,226,${dim})`, b: `rgba(248,113,113,${dim})` }
          if (bid === 'pass') return { c: `rgba(5,150,105,${dim})`, bg: `rgba(236,253,245,${dim})`, b: `rgba(110,231,183,${dim})` }
          return { c: `rgba(71,85,105,${dim})`, bg: `rgba(248,250,252,${dim})`, b: `rgba(203,213,225,${dim})` }
        }
        const btnSx = (bid, h, fs, disabled) => {
          const x = getBidColor(bid, disabled)
          return {
            minWidth: 0, flex: 1, height: h || 26, p: 0, fontSize: fs || '0.7rem', fontWeight: 600,
            color: x.c, bgcolor: x.bg, border: `1px solid ${x.b}`, borderRadius: '4px', textTransform: 'none',
            '&:hover': disabled ? {} : { filter: 'brightness(0.9)', border: `1px solid ${getBidColor(bid, false).c}` },
          }
        }
        // 使用外层 state 追踪选中的阶数（hooks 必须在顶层调用）
        return (
          <Box sx={{
            position: 'absolute',
            bottom: isMobile ? 8 : '5%',
            right: isMobile ? 8 : '3%',
            zIndex: 10,
            bgcolor: isDark ? 'rgba(17,24,39,0.88)' : 'rgba(255,255,255,0.88)',
            backdropFilter: 'blur(12px)', borderRadius: 2, p: 0.75,
            border: '1px solid', borderColor: 'divider',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            display: 'flex', flexDirection: 'column', gap: '4px',
            width: isMobile ? 130 : 200,
          }}>
            {/* 阶数选择：桌面一行，手机两行 */}
            {isMobile ? (
              <>
                <Box sx={{ display: 'flex', gap: '3px' }}>
                  {[1,2,3,4].map(l => {
                    const avail = levelAvailable(l)
                    const sel = selectedBidLevel === l
                    return (
                      <Button key={l} size="small"
                        sx={{ ...btnSx(l + 'NT', 24, '0.7rem', !avail), flex: 1,
                          ...(sel && avail ? { boxShadow: `0 0 0 2px ${getBidColor(l + 'NT', false).c}`, transform: 'scale(1.05)' } : {}),
                        }}
                        onClick={() => { if (avail) setSelectedBidLevel(sel ? null : l) }}
                        disabled={!avail}>{l}</Button>
                    )
                  })}
                </Box>
                <Box sx={{ display: 'flex', gap: '3px' }}>
                  {[5,6,7].map(l => {
                    const avail = levelAvailable(l)
                    const sel = selectedBidLevel === l
                    return (
                      <Button key={l} size="small"
                        sx={{ ...btnSx(l + 'NT', 24, '0.7rem', !avail), flex: 1,
                          ...(sel && avail ? { boxShadow: `0 0 0 2px ${getBidColor(l + 'NT', false).c}`, transform: 'scale(1.05)' } : {}),
                        }}
                        onClick={() => { if (avail) setSelectedBidLevel(sel ? null : l) }}
                        disabled={!avail}>{l}</Button>
                    )
                  })}
                  <Box sx={{ flex: 1, minWidth: 0 }} />
                </Box>
              </>
            ) : (
              <Box sx={{ display: 'flex', gap: '3px' }}>
                {[1,2,3,4,5,6,7].map(l => {
                  const avail = levelAvailable(l)
                  const sel = selectedBidLevel === l
                  return (
                    <Button key={l} size="small"
                      sx={{ ...btnSx(l + 'NT', 24, '0.7rem', !avail), flex: 1,
                        ...(sel && avail ? { boxShadow: `0 0 0 2px ${getBidColor(l + 'NT', false).c}`, transform: 'scale(1.05)' } : {}),
                      }}
                      onClick={() => { if (avail) setSelectedBidLevel(sel ? null : l) }}
                      disabled={!avail}>{l}</Button>
                  )
                })}
              </Box>
            )}
            {/* 行2: 花色选择 — 固定高度防止布局跳动 */}
            <Box sx={{ display: 'flex', gap: '3px', minHeight: 28 }}>
              {suits.map(s => {
                const lvl = selectedBidLevel || 1
                const avail = selectedBidLevel !== null && suitAvailable(lvl, s)
                const bid = lvl + s
                return (
                  <Button key={s} size="small" sx={btnSx(bid, 28, '0.7rem', !avail)}
                    onClick={() => { if (avail) { addBid && addBid(bid); setSelectedBidLevel(null) } }}
                    disabled={!avail || !addBid}>
                    {s === 'NT' ? 'NT' : s}
                  </Button>
                )
              })}
            </Box>
            {/* 行3: pass / X / XX */}
            <Box sx={{ display: 'flex', gap: '4px', minHeight: 28 }}>
              {['pass', 'X', 'XX'].map(bid => (
                <Button key={bid} size="small" sx={{ ...btnSx(bid, 28, '0.7rem', false), flex: 1 }}
                  onClick={() => { addBid && addBid(bid); setSelectedBidLevel(null) }}
                  disabled={!addBid}>
                  {bid}
                </Button>
              ))}
            </Box>
          </Box>
        )
      })()}

      {/* 人类无手牌时手动输入出牌 */}
      {showPlayPanel && playState && (() => {
        const cp = playState.current_player
        if (!cp) return null
        const isHuman = positionRoles?.[cp] === 'human' || (cp === playState.dummy && positionRoles?.[playState.contract?.declarer] === 'human')
        if (!isHuman) return null
        if (playState.phase === 'complete') return null
        if (!playInitiated) return null
        const isStartOfTrick = (playState.current_trick?.cards?.length || 0) === 0
        if (isPlayPaused && isStartOfTrick) return null
        const handLen = playState.hands?.[cp]?.length || 0
        if (handLen > 0) return null // 有手牌时用牌桌点击出牌
        const style = { bottom: isMobile ? 8 : '12%', right: isMobile ? 8 : '10%' }
        return (
          <Box sx={{ position: 'absolute', zIndex: 10, ...style, display: 'flex', gap: 0.5, alignItems: 'center', bgcolor: isDark ? 'rgba(17,24,39,0.88)' : 'rgba(255,255,255,0.88)', backdropFilter: 'blur(12px)', borderRadius: 2, p: 0.5, border: '1px solid', borderColor: 'divider', boxShadow: '0 4px 20px rgba(0,0,0,0.15)' }}>
            <TextField size="small" placeholder="♠A 或 SA"
              value={manualCardInput[cp] || ''}
              onChange={(e) => setManualCardInput(prev => ({ ...prev, [cp]: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (manualCardInput[cp] || '').trim()) {
                  onManualPlay?.(cp, (manualCardInput[cp] || '').trim())
                  setManualCardInput(prev => ({ ...prev, [cp]: '' }))
                }
              }}
              sx={{ width: 100, '& input': { fontSize: '0.75rem', textAlign: 'center', py: 0.5 } }}
            />
            <Button variant="contained" size="small"
              disabled={!(manualCardInput[cp] || '').trim()}
              onClick={() => {
                onManualPlay?.(cp, (manualCardInput[cp] || '').trim())
                setManualCardInput(prev => ({ ...prev, [cp]: '' }))
              }}
              sx={{ fontSize: '0.7rem', py: 0.3, px: 0.75, minWidth: 36 }}>出牌</Button>
          </Box>
        )
      })()}
    </Box>
  );
}

export default CardTable;
