import React, { useState, useMemo } from 'react';
import { Box, Button, CircularProgress, TextField, ToggleButton, ToggleButtonGroup, Typography, IconButton, Tooltip, useTheme, useMediaQuery } from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import HandDisplay from './HandDisplay';
import DoubleDummyTable from './DoubleDummyTable';
import { isHumanPosition, hasAnyHuman, getHumanPositions } from '../utils/position';

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
  colorScheme,
  currentBiddingPosition,
  showDoubleDummy,
  doubleDummyResult,
  doubleDummyLoading,
  biddingTotalTime,
  positionRoles,
  onPositionRoleChange,
  onDealerChange,
  onClearAllHands,
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
  aiBiddingHistory = [],
  onPlayCardClick,
  onSetPlayHand,
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

  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  const isDark = theme.palette.mode === 'dark'
  const textMuted = isDark ? '#94a3b8' : '#666'
  const textPrimary = isDark ? '#e2e8f0' : '#333'
  const handBoxSize = isMobile ? 'calc((100vw - 12px) * 0.42)' : 160
  const biddingTableWidth = isMobile ? 'calc((100vw - 12px) * 0.5)' : 160
  const centerBoxSize = isMobile ? 120 : 220

  if (!hands) return null;

  const north = hands['北'];
  const south = hands['南'];
  const east = hands['东'];
  const west = hands['西'];

  const defaultScheme = {
    table: {
      background: 'linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%)',
      border: '3px solid rgba(255, 255, 255, 0.5)',
      centerBg: 'rgba(255, 255, 255, 0.95)',
    },
    button: {
      primary: '#1976d2',
      primaryHover: '#1565c0',
      text: 'white',
    },
  }

  const scheme = {
    ...(colorScheme || defaultScheme),
    table: {
      ...((colorScheme || defaultScheme).table),
      ...(isDark ? {
        background: 'linear-gradient(135deg, #1a3a1c 0%, #0d1f0f 100%)',
        border: '3px solid rgba(255, 255, 255, 0.15)',
        centerBg: 'rgba(30, 41, 59, 0.95)',
      } : {}),
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

      // 有人类参与：AI手牌默认不显示，由checkbox控制
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

  const SUIT_COLORS = {
    '♠': '#000',
    '♥': '#e53935',
    '♦': '#e53935',
    '♣': '#000',
  };

  // 打牌阶段的叫牌过程表格（带tooltip显示叫牌含义）
  const renderPlayBiddingTable = () => {
    const positions = ['南', '西', '北', '东']

    // 构建 bid -> meaning 的映射（按位置和叫品匹配）
    const meaningMap = {}
    if (aiBiddingHistory && aiBiddingHistory.length > 0) {
      for (const record of aiBiddingHistory) {
        if (record.position && record.result?.bid != null) {
          const key = `${record.position}:${record.result.bid}`
          if (!meaningMap[key]) {
            meaningMap[key] = record.result.meaning || ''
          }
        }
      }
    }

    // 用 renderBiddingTable 的数据源（biddingSequence）来构建行
    // 但需要获取 biddingSequence —— 从 renderBiddingTable 间接获取不了
    // 所以从 aiBiddingHistory 提取序列
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
        fontFamily: '"Courier New", monospace',
        fontSize: '0.9rem',
      }}>
        <Box sx={{
          display: 'flex',
          justifyContent: 'space-around',
          borderBottom: isDark ? '2px solid rgba(255,255,255,0.2)' : '2px solid #333',
          paddingBottom: 0.5,
          marginBottom: 0.5,
          fontWeight: 'bold',
          color: textPrimary,
        }}>
          {positions.map(pos => (
            <Box key={pos} component="span" sx={{ flex: 1, textAlign: 'center', minWidth: 50, color: pos === dealer ? '#d32f2f' : 'inherit' }}>
              {pos}
            </Box>
          ))}
        </Box>
        {rows.map((row, rowIndex) => (
          <Box key={rowIndex} sx={{
            display: 'flex',
            justifyContent: 'space-around',
            padding: '4px 0',
            borderBottom: isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd',
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
                    backgroundColor: isDark ? 'rgba(99, 102, 241, 0.2)' : '#e3f2fd',
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
    
    // 优先显示当前墩（有牌时），暂停时才回退到上一墩
    const displayTrick = (current_trick?.cards && current_trick.cards.length > 0)
      ? current_trick
      : (isPlayPaused && lastCompletedTrick) ? lastCompletedTrick : current_trick
    
    const getCardAtPosition = (position) => {
      if (!displayTrick?.cards) return null
      const cardEntry = displayTrick.cards.find(([pos]) => pos === position)
      return cardEntry ? cardEntry[1] : null
    }
    
    const getLastTrickWinner = () => {
      if (isPlayPaused && lastCompletedTrick) {
        return lastCompletedTrick?.winner
      }
      return null
    }
    
    const renderCard = (position) => {
      const card = getCardAtPosition(position)
      
      if (!card) {
        return (
          <Box sx={{
            width: 44,
            height: 60,
            border: isDark ? '1px dashed rgba(255,255,255,0.15)' : '1px dashed #ccc',
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: isDark ? 'rgba(255,255,255,0.04)' : '#fafafa',
          }} />
        )
      }
      
      const color = SUIT_COLORS[card.suit] || '#000'
      const canClick = onPlayCardClick
      
      return (
        <Box
          onClick={() => canClick && onPlayCardClick(position, card)}
          sx={{
            width: 44,
            height: 60,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : '#fff',
            border: isDark ? '1px solid rgba(255,255,255,0.15)' : '1px solid #ddd',
            borderRadius: 1,
            boxShadow: 1,
            cursor: canClick ? 'pointer' : 'default',
            transition: 'all 0.15s',
            '&:hover': canClick ? { bgcolor: isDark ? 'rgba(99, 102, 241, 0.2)' : '#e3f2fd', transform: 'scale(1.05)' } : {},
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
        gap: 0.5,
      }}>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          {renderCard('北')}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 1 }}>
          {renderCard('西')}
          <Box sx={{ width: 60, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            {(displayTrick?.cards?.length === 4 && getLastTrickWinner()) ? (
              <Typography color="primary" sx={{ fontSize: '0.85rem', fontWeight: 'bold' }}>
                {getLastTrickWinner()}赢
              </Typography>
            ) : !isComplete && current_player ? (
              <Typography color="text.secondary" sx={{ fontSize: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                {current_player}出牌
                {aiLoading && (
                  <CircularProgress size={22} sx={{ position: 'absolute', top: '50%', left: '50%', marginTop: '-11px', marginLeft: '-11px', color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.45)' }} />
                )}
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
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = isAI && !hasHandData && (!biddingStarted || (stopBidding && !showPlayPanel))
    const isHuman = positionRoles && positionRoles[position] === 'human'
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const showAIHandInput = showPlayPanel && playState
      && isAI
      && (!playState.hands?.[position] || playState.hands[position].length === 0)
      && manualPlayedCount === 0
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
            bgcolor: 'rgba(0, 0, 0, 0.5)',
            borderRadius: '50%',
            p: 0.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <CircularProgress size={14} sx={{ color: '#ffeb3b' }} />
          </Box>
        )}
        
        <Box sx={{
          bgcolor: isDark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.98)',
          borderRadius: 2,
          p: isMobile ? 0.5 : 1,
          width: handBoxSize,
          height: handBoxSize,
          flexShrink: 0,
          boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
          display: 'flex',
          flexDirection: 'column',
          border: isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid rgba(255,255,255,0.5)',
          backdropFilter: 'blur(10px)',
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography 
              variant="subtitle2" 
              sx={{ 
                fontWeight: declarer === position ? 700 : 600, 
                fontSize: '0.85rem',
                color: declarer === position ? '#d32f2f' : 'inherit',
                cursor: onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel ? 'pointer' : 'default',
                transition: 'color 0.2s',
                '&:hover': onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel ? { color: 'primary.main' } : {}
              }}
              onClick={() => onDealerChange && (!biddingStarted || stopBidding) && !showPlayPanel && onDealerChange(position)}
            >
              {position}家
              {dealer === position && ' *'}
              {hasHandData && hand && hand.hcp !== undefined && !showInput && ` (${hand.hcp})`}
            </Typography>
            {onPositionRoleChange && (
              <ToggleButtonGroup
                value={positionRoles[position]}
                exclusive
                disabled={showPlayPanel && playInitiated && (!isPlayPaused || aiLoading) && !((playState?.current_trick?.cards?.length || 0) === 0 && !aiLoading)}
                onChange={(e, newRole) => {
                  if (newRole !== null) {
                    onPositionRoleChange(position, newRole)
                  }
                }}
                size="small"
                sx={{ 
                  height: 24,
                  '& .MuiToggleButton-root': {
                    px: 0.8,
                    py: 0.3,
                    fontSize: '0.7rem',
                    fontWeight: 500,
                    borderRadius: 1,
                  }
                }}
              >
                <ToggleButton value="ai" sx={{ minWidth: 32 }}>AI</ToggleButton>
                <ToggleButton value="human" sx={{ minWidth: 32 }}>人类</ToggleButton>
              </ToggleButtonGroup>
            )}
          </Box>
          
          {showInput ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
              {!handInputs[position] && (
                <Box sx={{
                  position: 'absolute',
                  top: '8px',
                  left: '8px',
                  pointerEvents: 'none',
                  fontSize: '0.75rem',
                  zIndex: 1,
                }}>
                  <span style={{ color: '#000' }}>♠</span>{' '}
                  <span style={{ color: '#d32f2f' }}>♥</span>{' '}
                  <span style={{ color: '#f57c00' }}>♦</span>{' '}
                  <span style={{ color: '#000' }}>♣</span>
                </Box>
              )}
              <TextField
                size="small"
                value={handInputs[position]}
                onChange={(e) => handleHandInputChange(position, e.target.value)}
                error={!!inputErrors[position]}
                helperText={inputErrors[position] || '如: AKQJ - T87 654'}
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
          ) : showAIHandInput ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
              {!handInputs[position] && (
                <Box sx={{
                  position: 'absolute',
                  top: '8px',
                  left: '8px',
                  pointerEvents: 'none',
                  fontSize: '0.75rem',
                  zIndex: 1,
                }}>
                  <span style={{ color: '#000' }}>♠</span>{' '}
                  <span style={{ color: '#d32f2f' }}>♥</span>{' '}
                  <span style={{ color: '#f57c00' }}>♦</span>{' '}
                  <span style={{ color: '#000' }}>♣</span>
                </Box>
              )}
              <TextField
                size="small"
                value={handInputs[position]}
                onChange={(e) => handleHandInputChange(position, e.target.value)}
                error={!!inputErrors[position]}
                helperText={inputErrors[position] || `输入${position}家完整手牌`}
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
                isActive={currentBidder === position}
                isHuman={isHuman}
                isDealer={dealer === position}
                isPartner={hasAnyHuman(positionRoles) && isHumanPosition(positionRoles, getPartnerPosition(position))}
                showContent={shouldShowHandContent(position)}
                hideTitle={true}
                playedCards={playedCardsSet}
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
      {onClearAllHands && gameMode !== 'pair' && !showPlayPanel && (!biddingStarted || (checkBiddingComplete && checkBiddingComplete())) && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 10,
        }}>
          <Tooltip title="模拟实战">
            <IconButton
              size="small"
              onClick={onClearAllHands}
              sx={{
                bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : 'rgba(255, 255, 255, 0.9)',
                color: isDark ? '#e2e8f0' : undefined,
                '&:hover': { bgcolor: isDark ? 'rgba(30, 41, 59, 1)' : 'rgba(255, 255, 255, 1)' }
              }}
            >
              <PlayArrowIcon />
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
          {outputFormatsLoading && <CircularProgress size={20} sx={{ color: 'white' }} />}
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
          
          <Box className="table-center" sx={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
            <Box className="table-border" sx={{
              width: biddingTableWidth,
              minWidth: biddingTableWidth,
              flexShrink: 0,
              minHeight: 80,
              border: scheme.table.border,
              borderRadius: 2,
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'flex-start',
              background: scheme.table.centerBg,
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
                border: scheme.table.border,
                borderRadius: 2,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                background: scheme.table.centerBg,
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
    </Box>
  );
}

export default CardTable;
