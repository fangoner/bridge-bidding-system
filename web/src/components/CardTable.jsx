import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import ReactDOM from 'react-dom';
import { Box, Button, Chip, CircularProgress, TextField, ToggleButton, ToggleButtonGroup, Typography, IconButton, Tooltip, useTheme, useMediaQuery, alpha } from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import BorderColorIcon from '@mui/icons-material/BorderColor'
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted'

import GridOnIcon from '@mui/icons-material/GridOn'
import HandDisplay from './HandDisplay';
import { getCardSuitColor } from '../constants/suits';
import DoubleDummyTable from './DoubleDummyTable';
import { isHumanPosition, hasAnyHuman, getHumanPositions, BRIDGE_POSITIONS } from '../utils/position';
import { useGame } from '../context/GameContext';

const MODEL_LABELS = {
  'deepseek-v4-flash': 'DSF',
  'deepseek-v4-pro': 'DSP',
  'doubao-seed-2.1-pro': 'DBP',
  'doubao-seed-2.1-turbo': 'DBT',
}

function modelVer(modelId) {
  const m = modelId.match(/v?(\d+(?:\.\d+)?)/)
  return m ? m[1] : ''
}

function modelLabel(modelId) {
  const abbr = MODEL_LABELS[modelId] || modelId.replace(/^deepseek-v4-/, 'DS').substring(0, 4)
  const ver = modelVer(modelId)
  return ver ? `${abbr} ${ver}` : abbr
}

// 牌桌默认配色 — 森林绿茵

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
  const { fallbackModel, playModel } = useGame()
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
  const [bidBoxPos, setBidBoxPos] = useState({ left: 0, top: 0, ready: false }) // Portal fixed位置
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
  // 统一间距（信息条↔中心面板=HAND_GAP，信息条↔手牌=INNER_GAP，四方向一致）
  const HAND_GAP = 8    // 信息条到中心面板的距离（四方向统一）
  const INNER_GAP = 0   // 信息条到手牌的间距

  // NS手牌容器（横向布局）
  const nsHandWidth = isMobile ? 'calc((100vw - 12px) * 0.88)' : 460
  const nsHandHeight = isMobile ? 'auto' : 'auto'
  // EW手牌容器（外层旋转90°后视觉为纵向）
  // 旋转前：横向布局，宽=totalFanLength, 高=cardHeight
  // 旋转后：视觉宽=cardHeight≈62px, 视觉高=totalFanLength≈460px
  // ewColW: 容器宽（旋转前=高），需容纳牌高+padding ≈ 80px
  // ewColH: 容器高度自适应，用 top/bottom 限制不溢出桌面
  const ewColW = 80
  const ewColH = 460
  const infoBarHeight = 24 // 信息条估计高度（旋转后视觉宽度）
  const biddingTableWidth = isMobile ? 'calc((100vw - 12px) * 0.5)' : 160
  const centerBoxSize = isMobile ? 120 : 220

  // 叫牌面板初始定位
  useEffect(() => {
    if (bidBoxPos.ready) return
    const t = setTimeout(() => {
      const center = document.querySelector('.card-table-container')
      if (center) {
        const rect = center.getBoundingClientRect()
        setBidBoxPos({
          left: rect.left + rect.width / 2 - 100,
          top: rect.top + rect.height / 2 + centerBoxSize / 2 + 20,
          ready: true,
        })
      } else {
        setBidBoxPos(p => ({ ...p, ready: true }))
      }
    }, 100)
    return () => clearTimeout(t)
  }, [bidBoxPos.ready, centerBoxSize])

  // Grid间距：手牌区到中心区的统一间距
  const GRID_GAP = isMobile ? 6 : 4

  if (!hands) return null;

  const north = hands['北'];
  const south = hands['南'];
  const east = hands['东'];
  const west = hands['西'];

  const defaultScheme = {
    table: {
      background: 'radial-gradient(ellipse at center, #3d7a58 0%, #25563b 40%, #1a3d28 100%)',
      border: '3px solid rgba(255, 255, 255, 0.12)',
      centerBg: 'rgba(255, 255, 255, 0.45)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 255, 255, 0.25)',
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

    const validCards = /^[AKQJTakqjt2-9-]+$/
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

    // 复盘模式：计算游标所在的墩序号和墩内牌序号
    let reviewTrickNum = 1
    let reviewCardInTrick = 1
    let displayTrickGlobalStart = 0  // displayTrick第一张牌之前的累计牌数
    if (isReview && playState?.tricks) {
      let accum = 0
      for (let i = 0; i < playState.tricks.length; i++) {
        const tlen = playState.tricks[i].cards?.length || 0
        if (reviewCursor < accum + tlen) {
          reviewTrickNum = i + 1
          reviewCardInTrick = reviewCursor - accum + 1
          displayTrickGlobalStart = accum
          break
        }
        accum += tlen
        reviewTrickNum = i + 2  // 游标在最后一墩之后（不应出现）
      }
    }

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

    // 判断某张牌（以position标识）是否在复盘游标之后
    const isCardAfterCursor = (position) => {
      if (!isReview || !displayTrick?.cards) return false
      const cardIdx = displayTrick.cards.findIndex(([pos]) => pos === position)
      if (cardIdx < 0) return false
      return displayTrickGlobalStart + cardIdx > reviewCursor
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

      const color = getCardSuitColor(card.suit)
      const afterCursor = isCardAfterCursor(position)

      return (
        <Box
          onClick={() => canClick && onPlayCardClick(position, card)}
          sx={{
            width: 44,
            height: 60,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: afterCursor ? '#e0e0e0' : '#fbfbf8',
            opacity: afterCursor ? 0.4 : 1,
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
              <Typography sx={{ fontSize: '0.7rem', fontWeight: 'bold', color: '#ffc107', textAlign: 'center', lineHeight: 1.2 }}>
                第{reviewTrickNum}墩<br/>第{reviewCardInTrick}张
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

  const InfoBar = ({ position, sx }) => {
    const hand = hands?.[position]
    const hasHandData = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs)
    const showInput = !readonlyMode && !showPlayPanel && isAIPosition(position) && !hasHandData && (!biddingStarted || stopBidding)
    const isCurrentlyBidding = currentBiddingPosition === position
    return (
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0,
        bgcolor: isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)',
        backdropFilter: 'blur(4px)', borderRadius: 1, px: 0.8, py: 0.2,
        ...sx,
      }}>
        {isCurrentlyBidding && (
          <CircularProgress size={12} sx={{ color: '#e53935' }} />
        )}
        <Typography variant="caption"
          onClick={(!readonlyMode && !showPlayPanel && onDealerChange) ? () => onDealerChange(position) : undefined}
          sx={{
            fontWeight: 700, fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333',
            cursor: (!readonlyMode && !showPlayPanel && onDealerChange) ? 'pointer' : 'default',
            userSelect: 'none',
          }}>
          {position}{dealer === position ? '*' : ''}
          {hasHandData && hand?.hcp !== undefined && !showInput ? ` ${hand.hcp}点` : ''}
        </Typography>
        {onPositionRoleChange && (
          <ToggleButton value="check" size="small"
            selected={positionRoles[position] === 'human'}
            disabled={(showPlayPanel && playInitiated && (!isPlayPaused || aiLoading) && !((playState?.current_trick?.cards?.length || 0) === 0 && !aiLoading)) || readonlyMode || (!showPlayPanel && biddingStarted && !hasHand(position))}
            onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
            sx={{ height: 18, px: 0.6, fontSize: '0.65rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
              bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover', color: 'text.primary',
            }}
          >{positionRoles[position] === 'human' ? '人类' : modelLabel(showPlayPanel ? playModel : fallbackModel)}</ToggleButton>
        )}
      </Box>
    )
  }

  // 独立手牌输入框（四家通用，绝对定位，距桌面边框30px）
  const renderIndependentHandInput = (position) => {
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = !readonlyMode && !showPlayPanel && isAI && !hasHandData && (!biddingStarted || stopBidding)
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const showPlayHandInput = !readonlyMode && showPlayPanel && playState
      && (!playState.hands?.[position] || playState.hands[position].length === 0)
      && manualPlayedCount === 0
      && !(position === playState.dummy && playState.phase === 'lead')
      && (isAI || position === playState.dummy)

    if (!showInput && !showPlayHandInput) return null

    // 四家定位：东西垂直居中，南北水平居中
    let positionStyle = {}
    if (position === '西') {
      positionStyle = { left: 0, top: '50%', transform: 'translateY(-50%)' }
    } else if (position === '东') {
      positionStyle = { right: 0, top: '50%', transform: 'translateY(-50%)' }
    } else if (position === '北') {
      positionStyle = { top: 0, left: '50%', transform: 'translateX(-50%)' }
    } else if (position === '南') {
      positionStyle = { bottom: 0, left: '50%', transform: 'translateX(-50%)' }
    }

    const helperText = showInput
      ? 'AKQJ T98 T87 654（用-缺门）'
      : `输入${position}家手牌（13张）`

    return (
      <Box sx={{
        position: 'absolute',
        ...positionStyle,
        zIndex: 100,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}>
        <TextField
          size="small"
          value={handInputs[position]}
          onChange={(e) => handleHandInputChange(position, e.target.value)}
          error={!!inputErrors[position]}
          helperText={inputErrors[position] || helperText}
          sx={{
            width: '120px',
            bgcolor: isDark ? 'rgba(255,255,255,0.05)' : '#ffffff',
            borderRadius: 1,
            '& .MuiInputBase-input': {
              fontSize: '0.75rem',
              padding: '4px',
              color: isDark ? '#f5f5f5' : '#1a1a1a',
            },
            '& .MuiFormHelperText-root': {
              fontSize: '0.6rem',
              margin: '2px 0 0 0',
              color: isDark ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.85)',
            },
            '& .MuiOutlinedInput-root': {
              '& fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.23)' },
              '&:hover fieldset': { borderColor: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.5)' },
            },
          }}
        />
        <Button
          size="small"
          variant="contained"
          sx={{ mt: 0.5, fontSize: '0.7rem', py: 0.3 }}
          onClick={() => showInput ? handleHandInputSubmit(position) : handleAIHandSubmit(position)}
          disabled={!handInputs[position].trim()}
        >
          确认
        </Button>
      </Box>
    )
  }

  // 独立"未知"控件（人类位置无手牌时显示，位于InfoBar与桌面边缘正中间）
  const renderIndependentUnknown = (position) => {
    const isHuman = positionRoles && positionRoles[position] === 'human'
    const hasHandData = hasHand(position)
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const handKnownInPlay = showPlayPanel && playState?.hands?.[position]?.length > 0
    // 明手首攻前无手牌有单独的[未知]显示，此处跳过避免重复
    const isDummyLeadUnknown = showPlayPanel && playState && position === playState.dummy && playState.phase === 'lead' && !hasHand(position)

    if (!isHuman || hasHandData || handKnownInPlay || manualPlayedCount > 0 || isDummyLeadUnknown) return null

    // InfoBar顶部边缘距桌面边缘：50% - (centerBoxSize/2 + HAND_GAP + infoBarHeight) = 50% - 142px
    // "未知"中心放在InfoBar顶部边缘与桌面边缘的正中间：25% - 71px
    // 用 translate(-50%, -50%) 让中心点定位
    let positionStyle = {}
    if (position === '西') {
      positionStyle = { left: 'calc(25% - 71px)', top: '50%', transform: 'translate(-50%, -50%)' }
    } else if (position === '东') {
      positionStyle = { left: 'calc(75% + 71px)', top: '50%', transform: 'translate(-50%, -50%)' }
    } else if (position === '北') {
      positionStyle = { top: 'calc(25% - 71px)', left: '50%', transform: 'translate(-50%, -50%)' }
    } else if (position === '南') {
      positionStyle = { top: 'calc(75% + 71px)', left: '50%', transform: 'translate(-50%, -50%)' }
    }

    return (
      <Box sx={{
        position: 'absolute',
        ...positionStyle,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <Typography sx={{
          fontSize: '1.4rem',
          fontWeight: 700,
          color: isDark ? '#f5f5f5' : '#1a1a1a',
          bgcolor: isDark ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(6px)',
          borderRadius: 1,
          px: 1.5,
          py: 0.5,
          border: isDark ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(0,0,0,0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '90px',
          height: '46px',
          boxSizing: 'border-box',
          whiteSpace: 'nowrap',
          lineHeight: 1,
        }}>
          未知
        </Typography>
      </Box>
    )
  }

  const renderHandWithStatus = (hand, position, sxProps) => {
    const orientation = sxProps?.orientation || 'horizontal'
    const popDirection = sxProps?.popDirection || 'auto'
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
      <Box sx={{
        ...sxProps,
        position: 'relative',
        bgcolor: 'transparent',
        p: 0,
        m: 0,
        overflow: 'visible',
        width: sxProps?.width || nsHandWidth,
        height: sxProps?.height || nsHandHeight,
        maxWidth: sxProps?.maxWidth || 'none',
        flexShrink: 0,
        boxShadow: 'none',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        border: 'none',
        borderRadius: 0,
        gap: 0,
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      }}>
          {/* 信息栏：可通过 noInfo 隐藏 */}
          {!sxProps?.noInfo && sxProps?.infoSide === 'top' && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: `${INNER_GAP}px`, flexShrink: 0,
              bgcolor: isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)',
              backdropFilter: 'blur(4px)', borderRadius: 1, px: 0.8, py: 0.2,
            }}>
              <Typography variant="caption" sx={{ fontWeight: 700, fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333' }}>
                {position}{dealer === position ? '*' : ''}
                {hasHandData && hand?.hcp !== undefined && !showInput ? ` ${hand.hcp}点` : ''}
              </Typography>
              {onPositionRoleChange && (
                <ToggleButton value="check" size="small"
                  selected={positionRoles[position] === 'human'}
                  disabled={(showPlayPanel && playInitiated && (!isPlayPaused || aiLoading) && !((playState?.current_trick?.cards?.length || 0) === 0 && !aiLoading)) || readonlyMode || (!showPlayPanel && biddingStarted && !hasHand(position))}
                  onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
                  sx={{ height: 18, px: 0.6, fontSize: '0.65rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
                    bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover', color: 'text.primary',
                  }}
                >{positionRoles[position] === 'human' ? '人类' : modelLabel(showPlayPanel ? playModel : fallbackModel)}</ToggleButton>
              )}
            </Box>
          )}
          
          {/* 明手首攻前无手牌 → 显示未知 */}
          {showPlayPanel && playState && position === playState.dummy && playState.phase === 'lead' && !hasHand(position) ? (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.8rem' }}>[未知]</Typography>
            </Box>
          ) : (showInput || showPlayHandInput) ? (
            /* 输入框由独立控件 renderIndependentHandInput 渲染，此处留空 */
            <Box sx={{ flex: 1 }} />
          ) : isHuman && !hasHandData && !handKnownInPlay && manualPlayedCount === 0 ? (
            /* "未知"由独立控件 renderIndependentUnknown 渲染，此处留空 */
            <Box sx={{ flex: 1 }} />
          ) : (
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
                orientation={orientation}
                popDirection={popDirection}
                enableHover={showPlayPanel && playState?.current_player === position && !!onHandCardClick}
              />
          )}
          {/* 信息栏（靠中心一侧）：infoSide='bottom'=在手牌下方 */}
          {!sxProps?.noInfo && (!sxProps?.infoSide || sxProps.infoSide === 'bottom') && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: `${INNER_GAP}px`, flexShrink: 0,
              bgcolor: isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)',
              backdropFilter: 'blur(4px)', borderRadius: 1, px: 0.8, py: 0.2,
            }}>
              <Typography variant="caption" sx={{ fontWeight: 700, fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333' }}>
                {position}{dealer === position ? '*' : ''}
                {hasHandData && hand?.hcp !== undefined && !showInput ? ` ${hand.hcp}点` : ''}
              </Typography>
              {onPositionRoleChange && (
                <ToggleButton value="check" size="small"
                  selected={positionRoles[position] === 'human'}
                  disabled={(showPlayPanel && playInitiated && (!isPlayPaused || aiLoading) && !((playState?.current_trick?.cards?.length || 0) === 0 && !aiLoading)) || readonlyMode || (!showPlayPanel && biddingStarted && !hasHand(position))}
                  onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
                  sx={{ height: 18, px: 0.6, fontSize: '0.65rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
                    bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover', color: 'text.primary',
                  }}
                >{positionRoles[position] === 'human' ? '人类' : modelLabel(showPlayPanel ? playModel : fallbackModel)}</ToggleButton>
              )}
            </Box>
          )}
        </Box>
    );
  };

  return (
    <Box className="card-table-container" sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isMobile ? 'stretch' : 'center',
      justifyContent: isMobile ? 'space-between' : 'center',
      p: isMobile ? '12px' : '30px',
      m: 0,
      background: scheme.table.background,
      borderRadius: 2,
      boxShadow: 'none',
      width: '100%',
      height: '100%',
      maxWidth: '100%',
      position: 'relative',
      overflow: 'visible',
      boxSizing: 'border-box',
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
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 0.5,
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-end' }}>
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
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-end' }}>
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
          flexDirection: 'column',
          gap: 0.5,
          alignItems: 'flex-end',
        }}>
          <Box sx={{ display: 'flex', gap: 0.5 }}>
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
          </Box>
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
            {renderHandWithStatus(north, '北', { width: '88vw', height: 'auto', maxWidth: '100%', mb: '6px', infoSide: 'bottom' })}
          </Box>

          <Box sx={{ display: 'flex', gap: '12px', width: '100%', mb: '6px', justifyContent: 'center' }}>
            {renderHandWithStatus(west, '西', { width: '43vw', height: 'auto', maxWidth: '100%', infoSide: 'bottom' })}
            {renderHandWithStatus(east, '东', { width: '43vw', height: 'auto', maxWidth: '100%', infoSide: 'bottom' })}
          </Box>

          <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
            {renderHandWithStatus(south, '南', { width: '88vw', height: 'auto', maxWidth: '100%', mb: '6px', infoSide: 'top' })}
          </Box>
          
          <Box className="table-center" sx={{ width: '100%', display: 'flex', justifyContent: isMobile ? 'flex-start' : 'center' }}>
            <Box className="table-border" sx={{
              width: biddingTableWidth,
              minWidth: biddingTableWidth,
              flexShrink: 0,
              minHeight: 80,
              maxHeight: 'none',
              p: 0,
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
        <Box sx={{
          // 桌面端布局容器（绿色桌面由外层card-table-container提供）
          position: 'relative',
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
        }}>
          {/* 中心面板：绝对定位居中，z-index高于手牌 */}
          <Box sx={{
            position: 'absolute',
            top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
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
            p: 0,
            overflowY: 'auto',
            zIndex: 50,
          }}>
            {renderCenterContent()}
          </Box>

          {/* 四个信息条：absolute 紧贴中心面板四边外侧，z-index 高于手牌 */}
          {/* 北：贴中心面板上方外侧，水平居中 */}
          <Box sx={{
            position: 'absolute',
            top: `calc(50% - ${centerBoxSize / 2}px - ${HAND_GAP}px - ${infoBarHeight / 2}px)`,
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
          }}>
            <InfoBar position="北" />
          </Box>
          {/* 南：贴中心面板下方外侧，水平居中 */}
          <Box sx={{
            position: 'absolute',
            top: `calc(50% + ${centerBoxSize / 2}px + ${HAND_GAP}px + ${infoBarHeight / 2}px)`,
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
          }}>
            <InfoBar position="南" />
          </Box>
          {/* 西：贴中心面板左侧外侧，垂直居中，信息条竖立 */}
          <Box sx={{
            position: 'absolute',
            top: '50%',
            left: `calc(50% - ${centerBoxSize / 2}px - ${HAND_GAP}px - ${infoBarHeight / 2}px)`,
            transform: 'translate(-50%, -50%) rotate(-90deg)',
            transformOrigin: 'center center',
            zIndex: 100,
            whiteSpace: 'nowrap',
          }}>
            <InfoBar position="西" />
          </Box>
          {/* 东：贴中心面板右侧外侧，垂直居中，信息条竖立 */}
          <Box sx={{
            position: 'absolute',
            top: '50%',
            left: `calc(50% + ${centerBoxSize / 2}px + ${HAND_GAP}px + ${infoBarHeight / 2}px)`,
            transform: 'translate(-50%, -50%) rotate(90deg)',
            transformOrigin: 'center center',
            zIndex: 100,
            whiteSpace: 'nowrap',
          }}>
            <InfoBar position="东" />
          </Box>

          {/* 北家手牌：距顶20px（外层padding已20px + 内部相对定位top=0 = 总20px），横向居中 */}
          <Box sx={{
            position: 'absolute',
            top: 0,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'fit-content',
            height: 'fit-content',
            zIndex: 10,
            border: 'none',
          }}>
            {renderHandWithStatus(north, '北', { width: 'auto', height: 'auto', maxWidth: 'none', noInfo: true, orientation: 'horizontal' })}
          </Box>

          {/* 南家手牌：距底20px（外层padding已20px + 内部相对定位bottom=0 = 总20px），横向居中 */}
          <Box sx={{
            position: 'absolute',
            bottom: 0,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'fit-content',
            height: 'fit-content',
            zIndex: 10,
            border: 'none',
          }}>
            {renderHandWithStatus(south, '南', { width: 'auto', height: 'auto', maxWidth: 'none', noInfo: true, orientation: 'horizontal' })}
          </Box>

          {/* 西家手牌：距左0（外层padding已20px），垂直居中，尺寸适配手牌 */}
          <Box sx={{
            position: 'absolute',
            left: 0,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 'fit-content',
            height: 'fit-content',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            overflow: 'visible',
            border: 'none',
          }}>
            {renderHandWithStatus(west, '西', { width: 'auto', height: 'auto', maxWidth: 'none', noInfo: true, orientation: 'vertical', popDirection: 'right' })}
          </Box>

          {/* 东家手牌：距右0（外层padding已20px），垂直居中，尺寸适配手牌 */}
          <Box sx={{
            position: 'absolute',
            right: 0,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 'fit-content',
            height: 'fit-content',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            overflow: 'visible',
            border: 'none',
          }}>
            {renderHandWithStatus(east, '东', { width: 'auto', height: 'auto', maxWidth: 'none', noInfo: true, orientation: 'vertical', popDirection: 'left' })}
          </Box>

          {/* 东西家独立手牌输入框：绝对定位，垂直居中，距桌面边框30px */}
          {renderIndependentHandInput('西')}
          {renderIndependentHandInput('东')}
          {/* 南北家独立手牌输入框：绝对定位，水平居中，距桌面边框30px */}
          {renderIndependentHandInput('北')}
          {renderIndependentHandInput('南')}
          {/* 四家独立"未知"控件：人类位置无手牌时显示 */}
          {renderIndependentUnknown('北')}
          {renderIndependentUnknown('南')}
          {renderIndependentUnknown('西')}
          {renderIndependentUnknown('东')}
        </Box>
      )}

      {/* 人类回合浮动叫牌面板 — Portal到body，全浏览器拖动 */}
      {!showPlayPanel && !showDoubleDummy && hasAnyHuman(positionRoles) && biddingStarted && (() => {
        const humanTurn = isHumanPosition(positionRoles, currentBidder)
        const biddingComplete = isBiddingCompleteFn ? isBiddingCompleteFn() : false
        if (!humanTurn || biddingComplete) return null
        if (!bidBoxPos.ready) return null // 等初始定位完成
        const suits = ['C', 'D', 'H', 'S', 'NT']
        const suitOrder = { C: 0, D: 1, H: 2, S: 3, NT: 4 }
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
        const levelAvailable = (l) => {
          if (l > minLevel) return true
          if (l === minLevel && minSuitIdx < 4) return true
          return false
        }
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

        const box = (
          <Box sx={{
            position: 'fixed',
            left: bidBoxPos.left,
            top: bidBoxPos.top,
            zIndex: 9999,
            bgcolor: isDark ? 'rgba(17,24,39,0.88)' : 'rgba(255,255,255,0.88)',
            backdropFilter: 'blur(12px)', borderRadius: 2, p: 0.75,
            border: '1px solid', borderColor: 'divider',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            display: 'flex', flexDirection: 'column', gap: '4px',
            width: isMobile ? 130 : 200,
            cursor: 'move',
            userSelect: 'none',
          }}
            onMouseDown={(e) => {
              if (e.target.tagName === 'BUTTON') return
              e.stopPropagation()
              // 记录拖拽起点
              const startX = e.clientX
              const startY = e.clientY
              const startLeft = bidBoxPos.left
              const startTop = bidBoxPos.top
              const handleMove = (ev) => {
                setBidBoxPos(p => ({
                  ...p,
                  left: startLeft + ev.clientX - startX,
                  top: startTop + ev.clientY - startY,
                }))
              }
              const handleUp = () => {
                window.removeEventListener('mousemove', handleMove)
                window.removeEventListener('mouseup', handleUp)
              }
              window.addEventListener('mousemove', handleMove)
              window.addEventListener('mouseup', handleUp)
            }}
          >
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
            {/* 行2: 花色选择 */}
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
        );
        return ReactDOM.createPortal(box, document.body);
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
