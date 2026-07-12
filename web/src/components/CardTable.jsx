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
import { calcScore } from '../utils/score';
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
  const [handPickerSelections, setHandPickerSelections] = useState({
    '南': {},
    '北': {},
    '东': {},
    '西': {}
  })
  const [handPickerSuit, setHandPickerSuit] = useState({
    '南': null,
    '北': null,
    '东': null,
    '西': null
  })
  const [handPickerPanelOpen, setHandPickerPanelOpen] = useState(false)
  const [handPickerPanelFor, setHandPickerPanelFor] = useState(null)
  const [playPanelPos, setPlayPanelPos] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [selectedBidLevel, setSelectedBidLevel] = useState(null)
  const [bidBoxPos, setBidBoxPos] = useState({ left: 0, top: 0, ready: false }) // Portal fixed位置
  const [mobileSelectedCard, setMobileSelectedCard] = useState(null) // 手机端双击出牌
  // 手动出牌输入已迁移为花色+牌点选择面板，无需 state
  // 出牌人变化时清除手机端选中
  useEffect(() => {
    setMobileSelectedCard(null)
    setPlayPanelPos(null)
  }, [playState?.current_player])

  // 出牌面板全局拖拽（fixed定位相对于视口）
  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      setPlayPanelPos({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
    }
    const onUp = () => setDragging(false)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [dragging, dragStart])

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
  const centerBoxWidth = isMobile ? 152 : 220
  const centerBoxHeight = isMobile ? 240 : 220
  const centerBoxSize = 220 // 桌面版中心面板宽高（包含 HAND_GAP 布局）

  // 叫牌面板初始定位
  useEffect(() => {
    if (bidBoxPos.ready) return
    const t = setTimeout(() => {
      const center = document.querySelector('.card-table-container')
      if (center) {
        const rect = center.getBoundingClientRect()
        setBidBoxPos({
          left: rect.left + rect.width / 2 - 100,
          top: rect.top + rect.height / 2 + centerBoxHeight / 2 + 20,
          ready: true,
        })
      } else {
        setBidBoxPos(p => ({ ...p, ready: true }))
      }
    }, 100)
    return () => clearTimeout(t)
  }, [bidBoxPos.ready, centerBoxHeight])

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
    // playedByPosition: 收集所有已出牌（全量，用于手牌重建）
    const playedByPosition = { '北': [], '东': [], '南': [], '西': [] }
    const allPlayed = []
    for (const trick of (playState.tricks || [])) {
      for (const [pos, card] of (trick.cards || [])) {
        allPlayed.push({ pos, card })
        playedByPosition[pos].push({ suit: card.suit, rank: card.rank })
      }
    }
    for (const [pos, card] of (playState.current_trick?.cards || [])) {
      allPlayed.push({ pos, card })
      playedByPosition[pos].push({ suit: card.suit, rank: card.rank })
    }
    // playedCardsSet: 用于手牌灰显。复盘模式只标记游标之前的牌，游标及之后的牌回到手牌
    const playedCardsSet = new Set()
    const limit = reviewCursor != null ? reviewCursor : allPlayed.length
    for (let i = 0; i < Math.min(limit, allPlayed.length); i++) {
      const { card } = allPlayed[i]
      playedCardsSet.add(card.suit + card.rank)
    }
    return { playedCardsSet, playedByPosition }
  }, [showPlayPanel, playState?.tricks, playState?.current_trick?.cards, reviewCursor])

  const getPlayedCardsSet = () => {
    return playedCardCache?.playedCardsSet ?? null
  }

  // 复盘模式：根据 reviewCursor 计算当前出牌者和当前墩信息
  // 游标语义：reviewCursor = N 表示前 N 张牌已出，第 N 张牌（allPlayed[N]）回到手牌加亮，轮到该位置出牌
  const POSITION_ORDER_ARR = ['南', '西', '北', '东']
  const reviewInfo = useMemo(() => {
    if (reviewCursor == null || !playState?.tricks) return null
    // 收集所有已出牌（完整记录）
    const allPlayed = []
    for (const t of playState.tricks) {
      for (const [pos, card] of (t.cards || [])) allPlayed.push({ pos, card })
    }
    for (const [pos, card] of (playState.current_trick?.cards || [])) allPlayed.push({ pos, card })

    // 当前出牌者 = allPlayed[reviewCursor].pos（游标位置的牌的出牌者）
    let currentPlayer = null
    if (reviewCursor < allPlayed.length) {
      currentPlayer = allPlayed[reviewCursor].pos
    }

    // 当前墩已出的牌 = 前 reviewCursor 张牌中属于当前墩的牌
    // 当前墩 = 第 (Math.floor(reviewCursor/4) + 1) 个墩，已有 (reviewCursor % 4) 张牌
    let trickCards = []
    let globalStart = 0
    let accum = 0
    for (let i = 0; i < playState.tricks.length; i++) {
      const tCards = playState.tricks[i].cards || []
      if (reviewCursor < accum + tCards.length) {
        // 游标在这个墩内部（部分已出）
        const idxInTrick = reviewCursor - accum
        trickCards = tCards.slice(0, Math.max(0, idxInTrick))  // 游标之前的牌（已出）
        globalStart = accum
        break
      }
      accum += tCards.length
    }
    // 所有 trick 都遍历完但未匹配，检查 current_trick
    if (trickCards.length === 0 && reviewCursor >= accum) {
      const ctCards = playState.current_trick?.cards || []
      if (ctCards.length > 0 && reviewCursor < accum + ctCards.length) {
        const idxInTrick = reviewCursor - accum
        trickCards = ctCards.slice(0, Math.max(0, idxInTrick))
        globalStart = accum
      }
      // 否则 trickCards 保持为空（首攻或游标在墩边界）
    }
    // 首攻（reviewCursor === 0）：trickCards 为空，currentPlayer 由 allPlayed[0].pos 给出
    return { currentPlayer, trickCards, globalStart, allPlayed }
  }, [reviewCursor, playState])

  const reviewCurrentPlayer = reviewInfo?.currentPlayer
  const reviewTrickGlobalStart = reviewInfo?.globalStart || 0

  // 计算当前可出的牌（跟花色规则）
  const playableCardSet = useMemo(() => {
    if (!showPlayPanel || !playState) return null
    // 复盘模式：phase 可能是 complete，但仍需要计算可出牌
    if (playState.phase === 'complete' && reviewCursor == null) return null
    const cp = reviewCursor != null ? reviewCurrentPlayer : playState.current_player
    if (!cp) return null
    // 复盘模式：playState.hands 可能为空，用顶层 hands 重建
    let hand = playState.hands?.[cp]
    if ((!hand || hand.length === 0) && reviewCursor != null && hands?.[cp]) {
      const suitMap = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }
      hand = []
      for (const suitKey of ['spades', 'hearts', 'diamonds', 'clubs']) {
        const suitStr = hands[cp][suitKey] || ''
        for (const rank of suitStr) {
          hand.push({ suit: suitMap[suitKey], rank: rank.toUpperCase() })
        }
      }
      // 游标 = N：前 N 张牌已出（allPlayed[0..N-1]），从手牌移除；游标位置及之后的牌保留（未出）
      const allPlayed = reviewInfo?.allPlayed || []
      const beforeCursor = allPlayed.slice(0, reviewCursor).filter(p => p.pos === cp)
      hand = hand.filter(c => !beforeCursor.some(p => p.card.suit === c.suit && p.card.rank === c.rank))
    }
    if (!hand || hand.length === 0) return null
    // 复盘模式：当前墩已出的牌需要从 reviewInfo 计算
    let trickCards = playState.current_trick?.cards || []
    if (reviewCursor != null && reviewInfo?.trickCards) {
      trickCards = reviewInfo.trickCards
    }
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
    // 调试日志：确认 playableCardSet 与 ddHints 的一致性
    if (reviewCursor != null) {
      console.log('[PLAYABLE-DEBUG]', {
        cp,
        handSize: hand.length,
        hand: hand.map(c => c.suit + c.rank),
        ledSuit: trickCards.length > 0 ? trickCards[0][1]?.suit : null,
        trickCards: trickCards.map(([p, c]) => [p, c.suit + c.rank]),
        playableSet: Array.from(set),
        reviewCursor,
      })
    }
    return set
  }, [showPlayPanel, playState, reviewCursor, reviewCurrentPlayer, reviewInfo, hands])

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
        fontWeight: 600,
      }}>
        <Box sx={{
          display: 'flex',
          justifyContent: 'center',
          gap: isMobile ? 1 : 0,
          borderBottom: `2px solid ${theme.palette.text.primary}`,
          paddingBottom: isMobile ? 1 : 1,
          marginBottom: isMobile ? 0.5 : 1,
          fontWeight: 'bold',
          color: textPrimary,
          position: 'sticky',
          top: 0,
          zIndex: 2,
        }}>
          {positions.map(pos => (
            <Box key={pos} component="span" sx={{ flex: 1, textAlign: 'center', minWidth: isMobile ? 30 : 50, color: pos === dealer ? theme.palette.error.main : 'inherit' }}>
              {pos}
            </Box>
          ))}
        </Box>
        {rows.map((row, rowIndex) => (
          <Box key={rowIndex} sx={{
            display: 'flex',
            justifyContent: 'center',
            gap: isMobile ? 1 : 0,
            padding: '4px 0',
            borderBottom: `1px solid ${theme.palette.divider}`,
            '&:last-child': { borderBottom: 'none' },
          }}>
            {positions.map((pos, colIndex) => {
              const bid = row.bids[colIndex]
              const meaning = row.info[colIndex]
              const displayText = !bid ? '' : (bid === 'pass' ? 'P' : bid)
              const cellEl = (
                <Box
                  key={colIndex}
                  component="span"
                  className={`bidding-cell ${bid ? 'has-bid' : ''}`}
                  sx={{
                    flex: 1,
                    textAlign: 'center',
                    minWidth: isMobile ? 30 : 50,
                    fontWeight: 500,
                    color: textPrimary,
                    backgroundColor: bid ? alpha(theme.palette.primary.main, 0.08) : 'transparent',
                    borderRadius: 1,
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

    // 首攻位置：第一张牌的出牌者
    const allPlayedFirstPos = playState?.tricks?.[0]?.cards?.[0]?.[0] || null

    // 复盘模式：计算游标所在的墩序号和墩内牌序号
    // 游标语义：reviewCursor = N 表示前 N 张牌已出，第 N 张（allPlayed[N]，0-based）回到手牌加亮
    // 显示规则与 reviewTrick (CardTablePanel) 一致：
    // - cardInTrick > 0：显示当前墩（部分牌已出）
    // - cardInTrick == 0：显示上一墩（完整 4 张）
    // - N == totalCards：显示最后一墩（完整 4 张）
    let reviewTrickNum = 1
    let reviewCardInTrick = 1
    let displayTrickGlobalStart = 0  // displayTrick第一张牌之前的累计牌数
    let displayTrickIdx = -1
    let cursorAtStart = false  // 游标在某墩开头（首攻或墩边界）
    if (isReview && playState?.tricks && playState.tricks.length > 0) {
      let accum = 0
      for (let i = 0; i < playState.tricks.length; i++) {
        const tLen = playState.tricks[i].cards?.length || 0
        if (reviewCursor < accum + tLen) {
          const cardInTrick = reviewCursor - accum
          if (cardInTrick === 0) {
            // 游标在该墩开头，显示上一墩（若 i=0 则无上一墩，首攻）
            cursorAtStart = true
            displayTrickIdx = i - 1
            reviewTrickNum = i  // 显示第 i-1 墩（1-based: i）
            reviewCardInTrick = (i > 0 ? (playState.tricks[i - 1].cards?.length || 0) : 0)
          } else {
            // 游标在该墩内部，显示该墩
            displayTrickIdx = i
            reviewTrickNum = i + 1
            reviewCardInTrick = cardInTrick  // 已出牌数 = 显示的第 Y 张
          }
          break
        }
        accum += tLen
      }
      // 只有游标在所有 trick 之后（全部已出）且不是首攻时，才显示最后一墩
      if (displayTrickIdx === -1 && !cursorAtStart) {
        displayTrickIdx = playState.tricks.length - 1
        reviewTrickNum = displayTrickIdx + 1
        reviewCardInTrick = playState.tricks[displayTrickIdx].cards?.length || 0
      }
      // displayTrickGlobalStart = displayTrickIdx 之前所有墩的牌数总和
      for (let i = 0; i < displayTrickIdx; i++) {
        displayTrickGlobalStart += playState.tricks[i].cards?.length || 0
      }
    }

    // 复盘模式：显示 reviewTrick；否则优先当前墩，再 lastCompletedTrick
    const displayTrick = isReview
      ? (reviewTrick || { cards: [] })  // 复盘模式：用 reviewTrick，墩边界时显示空墩（首攻）
      : (current_trick?.cards && current_trick.cards.length > 0)
        ? current_trick
        : lastCompletedTrick ? lastCompletedTrick : current_trick

    const getCardAtPosition = (position) => {
      if (!displayTrick?.cards) return null
      const cardEntry = displayTrick.cards.find(([pos]) => pos === position)
      return cardEntry ? cardEntry[1] : null
    }

    // 判断某张牌（以position标识）是否在复盘游标处或之后（应回到手牌，不在桌面显示）
    const isCardAfterCursor = (position) => {
      if (!isReview || !displayTrick?.cards) return false
      const cardIdx = displayTrick.cards.findIndex(([pos]) => pos === position)
      if (cardIdx < 0) return false
      return displayTrickGlobalStart + cardIdx >= reviewCursor
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

      // 复盘模式：游标处及之后的牌回到手牌，桌面显示空位
      const afterCursor = isCardAfterCursor(position)
      if (!card || afterCursor) {
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
              displayTrickIdx < 0 ? (
                // 首攻（游标在第1墩开头）：显示首攻位置
                <Typography sx={{ fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.75)', textAlign: 'center' }}>
                  {reviewCurrentPlayer || allPlayedFirstPos || '首攻'}<br/>出牌
                </Typography>
              ) : (
                <Typography sx={{ fontSize: '0.7rem', fontWeight: 'bold', color: '#ffc107', textAlign: 'center', lineHeight: 1.2 }}>
                  第{reviewTrickNum}墩<br/>第{reviewCardInTrick}张
                </Typography>
              )
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
    const showInput = !showPlayPanel && isAIPosition(position) && !hasHandData && (!biddingStarted || stopBidding)
    const isCurrentlyBidding = currentBiddingPosition === position
    const isDeclarerInfo = showPlayPanel && playState?.contract?.declarer === position
    return (
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0,
        bgcolor: isDeclarerInfo
          ? '#FFB6C1'
          : (isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)'),
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
        </Typography>
        {hasHandData && hand?.hcp !== undefined && !showInput && shouldShowHandContent(position) && (
          <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.75rem', color: isDark ? '#fbbf24' : '#d97706' }}>
            {hand.hcp}点
          </Typography>
        )}
        {onPositionRoleChange && (
          <ToggleButton value="check" size="small"
            selected={positionRoles[position] === 'human'}
            disabled={(!showPlayPanel && biddingStarted && !stopBidding && !hasHand(position))}
            onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
            sx={{ height: 18, px: 0.6, fontSize: '0.75rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
              bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover',
              color: positionRoles[position] === 'human' ? '#6366f1' : (isDark ? '#60a5fa' : '#2563eb'),
            }}
          >{positionRoles[position] === 'human' ? '人类' : modelLabel(showPlayPanel ? playModel : fallbackModel)}</ToggleButton>
        )}
      </Box>
    )
  }

  // 共享手牌选牌面板（独立居中，点击TextField后激活）
  const renderHandPickerPanel = () => {
    const position = handPickerPanelFor
    if (!handPickerPanelOpen || !position) return null

    const selections = handPickerSelections[position] || {}
    const selectedCards = Object.keys(selections)
    const selectedCount = selectedCards.length

    const pickSuit = handPickerSuit[position]
    const setPickSuit = (s) => setHandPickerSuit(prev => ({ ...prev, [position]: s }))

    const takenSet = new Set()
    for (const [pos, hand] of Object.entries(hands || {})) {
      if (pos === position || !hand || typeof hand !== 'object') continue
      for (const [sk, sr] of Object.entries(hand)) {
        if (!sr || sr === '-' || typeof sr !== 'string') continue
        const ss = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[sk] || sk
        for (const r of sr) takenSet.add(`${ss}${r}`)
      }
    }

    const toggleCard = (suit, rank) => {
      const cardKey = suit + rank
      if (takenSet.has(cardKey)) return
      setHandPickerSelections(prev => {
        const cur = { ...(prev[position] || {}) }
        if (cur[cardKey]) {
          delete cur[cardKey]
        } else {
          if (Object.keys(cur).length >= 13) return prev
          cur[cardKey] = true
        }
        return { ...prev, [position]: cur }
      })
      setInputErrors(prev => ({ ...prev, [position]: '' }))
    }

    const clearAll = () => {
      setHandPickerSelections(prev => ({ ...prev, [position]: {} }))
      setHandPickerSuit(prev => ({ ...prev, [position]: null }))
      setInputErrors(prev => ({ ...prev, [position]: '' }))
    }

    const closePanel = () => {
      setHandPickerPanelOpen(false)
      setHandPickerPanelFor(null)
      setHandPickerSuit(prev => ({ ...prev, [position]: null }))
    }

    const handleConfirm = () => {
      if (selectedCount !== 13) {
        setInputErrors(prev => ({ ...prev, [position]: `已选${selectedCount}张，需要13张` }))
        return
      }

      const bySuit = { '♠': [], '♥': [], '♦': [], '♣': [] }
      for (const ck of selectedCards) {
        const s = ck[0]
        if (bySuit[s]) bySuit[s].push(ck.slice(1))
      }
      const ro = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
      for (const s of Object.keys(bySuit)) bySuit[s].sort((a, b) => ro.indexOf(a) - ro.indexOf(b))

      const suitMap = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
      const hand = {}
      let hcp = 0
      const hcpMap = { 'A': 4, 'K': 3, 'Q': 2, 'J': 1 }
      for (const [s, ranks] of Object.entries(bySuit)) {
        hand[suitMap[s]] = ranks.join('')
        for (const r of ranks) hcp += (hcpMap[r] || 0)
      }
      hand.hcp = hcp

      const dup = new Map()
      for (const [pos, h] of Object.entries(hands || {})) {
        if (pos === position || !h || typeof h !== 'object') continue
        for (const [sk, sr] of Object.entries(h)) {
          if (!sr || sr === '-' || typeof sr !== 'string') continue
          const s2 = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[sk] || sk
          for (const r of sr) dup.set(`${s2}${r}`, pos)
        }
      }
      for (const ck of selectedCards) {
        if (dup.has(ck)) {
          setInputErrors(prev => ({ ...prev, [position]: `${ck} 已在${dup.get(ck)}家手牌中` }))
          return
        }
      }

      const isAI2 = isAIPosition(position)
      const showInput = !showPlayPanel && isAI2 && !hasHand(position) && (!biddingStarted || stopBidding)
      if (showInput) {
        setHands(prev => ({ ...prev, [position]: hand }))
      } else {
        onSetPlayHand?.(position, hand)
      }

      setHandPickerSelections(prev => ({ ...prev, [position]: {} }))
      setHandPickerSuit(prev => ({ ...prev, [position]: null }))
      setHandPickerPanelOpen(false)
      setHandPickerPanelFor(null)
    }

    const bySuitDisplay = { '♠': [], '♥': [], '♦': [], '♣': [] }
    for (const ck of selectedCards) {
      const s = ck[0]
      if (bySuitDisplay[s]) bySuitDisplay[s].push(ck.slice(1))
    }
    for (const s of Object.keys(bySuitDisplay)) bySuitDisplay[s].sort((a, b) => ro.indexOf(a) - ro.indexOf(b))

    const suits = [
      { s: '♠', c: isDark ? '#cbd5e1' : '#1a1a2e' },
      { s: '♥', c: '#dc2626' },
      { s: '♦', c: '#7c3aed' },
      { s: '♣', c: isDark ? '#cbd5e1' : '#1a1a2e' },
    ]
    const ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
    const rd = (r) => r === 'T' ? '10' : r

    const btnBase = (w, h, fs) => ({
      minWidth: 0, width: w, height: h, p: 0,
      fontSize: fs, fontWeight: 600, borderRadius: 0.5,
    })

    return (
      <Box sx={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        bgcolor: 'rgba(0,0,0,0.3)',
      }} onClick={closePanel}>
        <Box sx={{
          bgcolor: isDark ? 'rgba(17,24,39,0.97)' : 'rgba(255,255,255,0.97)',
          backdropFilter: 'blur(12px)', borderRadius: 2, p: 1.5,
          border: '1px solid', borderColor: 'divider',
          boxShadow: '0 8px 32px rgba(0,0,0,0.35)',
          display: 'flex', flexDirection: 'column', gap: 0.5,
          width: 380,
        }} onClick={e => e.stopPropagation()}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 0.5 }}>
            <Typography sx={{ fontSize: '0.85rem', fontWeight: 700, color: isDark ? '#e2e8f0' : '#333' }}>
              {position}家 手牌 ({selectedCount}/13)
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <Button size="small" onClick={clearAll} disabled={selectedCount === 0}
                sx={{ fontSize: '0.6rem', py: 0.1, px: 0.8, minWidth: 0, height: 22 }}>清空</Button>
              <Button size="small" variant="contained" onClick={handleConfirm}
                disabled={selectedCount !== 13}
                sx={{ fontSize: '0.6rem', py: 0.1, px: 1, minWidth: 0, height: 22 }}>确认</Button>
            </Box>
          </Box>

          {selectedCount > 0 && (
            <Box sx={{ px: 0.5, fontFamily: 'monospace', fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333' }}>
              {suits.map(({ s, c }) => (
                <span key={s}>
                  <span style={{ color: c }}>{s}</span>
                  {bySuitDisplay[s].length > 0 ? bySuitDisplay[s].join('') : '-'}
                  {' '}
                </span>
              ))}
            </Box>
          )}

          {inputErrors[position] && (
            <Typography sx={{ fontSize: '0.68rem', color: '#dc2626', px: 0.5 }}>{inputErrors[position]}</Typography>
          )}

          <Box sx={{ display: 'flex', gap: 0.5, px: 0.5, justifyContent: 'center' }}>
            {suits.map(({ s, c }) => (
              <Button key={s} size="small"
                variant={pickSuit === s ? 'contained' : 'outlined'}
                onClick={() => setPickSuit(pickSuit === s ? null : s)}
                sx={{
                  ...btnBase(44, 34, '1.1rem'),
                  color: pickSuit === s ? '#fff' : c,
                  borderColor: pickSuit === s ? '#6366f1' : (isDark ? '#334155' : '#ccc'),
                  bgcolor: pickSuit === s ? '#6366f1' : 'transparent',
                  '&:hover': { bgcolor: pickSuit === s ? '#818cf8' : (isDark ? '#334155' : '#f0f0f0') },
                }}
              >{s}</Button>
            ))}
          </Box>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.3, px: 0.5, justifyContent: 'center' }}>
            {ranks.map((rank) => {
              const cardKey = pickSuit ? pickSuit + rank : null
              const sel = cardKey && !!selections[cardKey]
              const taken = cardKey && takenSet.has(cardKey)
              return (
                <Button key={rank} size="small"
                  disabled={taken || !pickSuit}
                  onClick={() => pickSuit && toggleCard(pickSuit, rank)}
                  sx={{
                    ...btnBase(30, 30, '0.7rem'),
                    color: taken ? (isDark ? '#64748b' : '#aaa')
                      : sel ? '#fff' : (isDark ? '#cbd5e1' : '#333'),
                    borderColor: taken ? (isDark ? '#374151' : '#ddd')
                      : sel ? '#ef4444' : (isDark ? '#334155' : '#ccc'),
                    bgcolor: taken ? 'transparent'
                      : sel ? (isDark ? '#dc2626' : '#ef4444') : 'transparent',
                    '&:hover': { bgcolor: taken ? 'transparent'
                      : sel ? '#f87171' : (isDark ? '#334155' : '#f0f0f0') },
                    '&.Mui-disabled': { color: isDark ? '#475569' : '#bbb', borderColor: isDark ? '#374151' : '#ddd' },
                  }}
                >{rd(rank)}</Button>
              )
            })}
          </Box>
        </Box>
      </Box>
    )
  }

  // 独立手牌输入框（TextField + 选牌按钮）
  const renderIndependentHandInput = (position) => {
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = !showPlayPanel && isAI && !hasHandData && (!biddingStarted || stopBidding)
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const showPlayHandInput = showPlayPanel && playState
      && (!playState.hands?.[position] || playState.hands[position].length === 0)
      && manualPlayedCount === 0
      && !(position === playState.dummy && playState.phase === 'lead')
      && (isAI || position === playState.dummy)

    if (!showInput && !showPlayHandInput) return null

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
            width: '140px',
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
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
          <Button
            size="small"
            variant="outlined"
            sx={{ fontSize: '0.65rem', py: 0.2, px: 0.8 }}
            onClick={() => {
              setHandPickerPanelFor(position)
              setHandPickerPanelOpen(true)
            }}
          >
            选牌
          </Button>
          <Button
            size="small"
            variant="contained"
            sx={{ fontSize: '0.65rem', py: 0.2, px: 0.8 }}
            onClick={() => showInput ? handleHandInputSubmit(position) : handleAIHandSubmit(position)}
            disabled={!handInputs[position].trim()}
          >
            确认
          </Button>
        </Box>
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
    const currentTurnPos = showPlayPanel ? (reviewCursor != null ? reviewCurrentPlayer : playState?.current_player) : currentBiddingPosition;
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = !showPlayPanel && isAI && !hasHandData && (!biddingStarted || stopBidding)
    const isHuman = positionRoles && positionRoles[position] === 'human'
    const manualPlayedCount = showPlayPanel ? getManualPlayedCards(position).length : 0
    const showPlayHandInput = showPlayPanel && playState
      && (!playState.hands?.[position] || playState.hands[position].length === 0)
      && manualPlayedCount === 0
      && !(position === playState.dummy && playState.phase === 'lead')
      && (isAI || position === playState.dummy)
    const handKnownInPlay = showPlayPanel && playState?.hands?.[position]?.length > 0
    const isDeclarer = showPlayPanel && playState?.contract?.declarer === position
    
    // 人类庄家手动出牌模式（庄家手牌未知）：明手在非明手回合时变灰，提示用户用选择面板出庄家的牌
    const humanDeclarerManualMode = showPlayPanel && playState
      && playState.contract?.declarer
      && positionRoles?.[playState.contract.declarer] === 'human'
      && (!playState.hands?.[playState.contract.declarer] || playState.hands[playState.contract.declarer].length === 0)
    const isDummyDimmed = humanDeclarerManualMode
      && position === playState.dummy
      && playState.current_player !== playState.dummy
      && playState.phase !== 'complete'
    
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
        ...(currentTurnPos === position && {
          boxShadow: `0 0 0 2px ${theme.palette.primary.main}, 0 4px 14px rgba(0,0,0,0.2)`,
          borderRadius: '8px',
        }),
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      }}>
          {/* 信息栏：可通过 noInfo 隐藏 */}
          {!sxProps?.noInfo && sxProps?.infoSide === 'top' && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: `${INNER_GAP}px`, flexShrink: 0,
              bgcolor: isDeclarer
                ? '#FFB6C1'
                : (isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)'),
              backdropFilter: 'blur(4px)', borderRadius: 1, px: 0.8, py: 0.2,
            }}>
              <Typography variant="caption" sx={{ fontWeight: 700, fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333' }}>
                {position}{dealer === position ? '*' : ''}
              </Typography>
              {hasHandData && hand?.hcp !== undefined && !showInput && shouldShowHandContent(position) && (
                <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.75rem', color: isDark ? '#fbbf24' : '#d97706' }}>
                  {hand.hcp}点
                </Typography>
              )}
              {onPositionRoleChange && (
                <ToggleButton value="check" size="small"
                  selected={positionRoles[position] === 'human'}
                  disabled={(!showPlayPanel && biddingStarted && !stopBidding && !hasHand(position))}
                  onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
                  sx={{ height: 18, px: 0.6, fontSize: '0.75rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
                    bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover',
                    color: positionRoles[position] === 'human' ? '#6366f1' : (isDark ? '#60a5fa' : '#2563eb'),
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
                isActive={showPlayPanel ? (reviewCursor != null ? reviewCurrentPlayer === position : playState?.current_player === position) : currentBidder === position}
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
                enableHover={showPlayPanel && (reviewCursor != null
                  ? reviewCurrentPlayer === position
                  : playState?.current_player === position && !!onHandCardClick)}
                dimmed={isDummyDimmed}
              />
          )}
          {/* 信息栏（靠中心一侧）：infoSide='bottom'=在手牌下方 */}
          {!sxProps?.noInfo && (!sxProps?.infoSide || sxProps.infoSide === 'bottom') && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: `${INNER_GAP}px`, flexShrink: 0,
              bgcolor: isDeclarer
                ? '#FFB6C1'
                : (isDark ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.7)'),
              backdropFilter: 'blur(4px)', borderRadius: 1, px: 0.8, py: 0.2,
            }}>
              <Typography variant="caption" sx={{ fontWeight: 700, fontSize: '0.75rem', color: isDark ? '#e2e8f0' : '#333' }}>
                {position}{dealer === position ? '*' : ''}
              </Typography>
              {hasHandData && hand?.hcp !== undefined && !showInput && shouldShowHandContent(position) && (
                <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.75rem', color: isDark ? '#fbbf24' : '#d97706' }}>
                  {hand.hcp}点
                </Typography>
              )}
              {onPositionRoleChange && (
                <ToggleButton value="check" size="small"
                  selected={positionRoles[position] === 'human'}
                  disabled={(!showPlayPanel && biddingStarted && !stopBidding && !hasHand(position))}
                  onChange={() => onPositionRoleChange(position, positionRoles[position] === 'human' ? 'ai' : 'human')}
                  sx={{ height: 18, px: 0.6, fontSize: '0.75rem', fontWeight: 600, borderRadius: 1, minWidth: 30, border: 'none',
                    bgcolor: positionRoles[position] === 'human' ? 'rgba(91,95,227,0.15)' : 'action.hover',
                    color: positionRoles[position] === 'human' ? '#6366f1' : (isDark ? '#60a5fa' : '#2563eb'),
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
      alignItems: 'center',
      justifyContent: 'center',
      p: isMobile ? '0' : '30px',
      m: 0,
      background: scheme.table.background,
      borderRadius: 2,
      boxShadow: 'none',
      width: '100%',
      height: isMobile
        ? `calc(30px + 74px + 60px + ${infoBarHeight}px + 3px + ${centerBoxHeight}px + 3px + ${infoBarHeight}px + 60px + 74px + 30px)`
        : '100%',
      maxWidth: '100%',
      position: 'relative',
      overflow: isMobile ? 'hidden' : 'visible',
      boxSizing: 'border-box',
      }}>
      {/* 模拟实战清空按钮：任何阶段可见可点击（叫牌/打牌均可） */}
      {onSimulatedReset && gameMode !== 'pair' && (
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
            {onClearAllHands && !showPlayPanel && (
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
            {onEditHands && !showPlayPanel && (
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
            {onEditBidding && !showPlayPanel && (
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
            {handleAnalyzeContract && outputFormats && !showPlayPanel && ['南','北','东','西'].every(pos => {
              const h = hands?.[pos]
              if (!h) return false
              return (h.spades?.length || 0) + (h.hearts?.length || 0) + (h.diamonds?.length || 0) + (h.clubs?.length || 0) === 13
            }) && (
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
            {(() => {
              const suit = playState.contract.suit || 'NT'
              const suitColor = { '♠': '#1a1a2e', '♥': '#d32f2f', '♦': '#7c3aed', '♣': '#1a1a2e', 'NT': '#1a1a2e' }[suit] || '#1a1a2e'
              return (
                <Chip
                  label={`${playState.contract.level || '?'}${suit}${playState.contract.redoubled ? 'XX' : playState.contract.doubled ? 'X' : ''}`}
                  size="small"
                  sx={{ fontSize: '0.7rem', bgcolor: 'rgba(255,255,255,0.92)', color: suitColor, fontWeight: 700 }}
                />
              )
            })()}
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
        <Box sx={{
          position: 'relative',
          width: '100%',
          height: '100%',
          boxSizing: 'border-box',
        }}>
          {/* 中心面板：绝对定位居中 */}
          <Box sx={{
            position: 'absolute',
            top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            width: centerBoxWidth,
            height: centerBoxHeight,
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

          {/* 北家手牌：距顶40px，向中心移动 */}
          <Box sx={{
            position: 'absolute',
            top: '40px', left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
          }}>
            {renderHandWithStatus(north, '北', { width: 'auto', height: 'auto', noInfo: true })}
          </Box>
          {/* 北家信息条：中心面板上方 */}
          <Box sx={{
            position: 'absolute',
            top: `calc(50% - ${centerBoxHeight / 2}px - 3px - ${infoBarHeight / 2}px)`,
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
          }}>
            <InfoBar position="北" />
          </Box>

          {/* 南家手牌：距底40px（与北向中心移动对称） */}
          <Box sx={{
            position: 'absolute',
            bottom: '40px', left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
          }}>
            {renderHandWithStatus(south, '南', { width: 'auto', height: 'auto', noInfo: true })}
          </Box>
          {/* 南家信息条：中心面板下方 */}
          <Box sx={{
            position: 'absolute',
            top: `calc(50% + ${centerBoxHeight / 2}px + 3px + ${infoBarHeight / 2}px)`,
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
          }}>
            <InfoBar position="南" />
          </Box>

          {/* 西家手牌：左溢出一半宽度，只显示靠中心的一半 */}
          <Box sx={{
            position: 'absolute',
            left: '-37px', top: '50%',
            transform: 'translateY(-50%)',
            zIndex: 10,
          }}>
            {renderHandWithStatus(west, '西', { width: 'auto', height: 'auto', noInfo: true, orientation: 'vertical', popDirection: 'right' })}
          </Box>
          {/* 西家信息条：中心面板左侧，旋转-90° */}
          <Box sx={{
            position: 'absolute',
            top: '50%',
            left: `calc(50% - ${centerBoxWidth / 2}px - 3px - ${infoBarHeight / 2}px)`,
            transform: 'translate(-50%, -50%) rotate(-90deg)',
            transformOrigin: 'center center',
            zIndex: 100,
            whiteSpace: 'nowrap',
          }}>
            <InfoBar position="西" />
          </Box>

          {/* 东家手牌：右溢出一半宽度，只显示靠中心的一半 */}
          <Box sx={{
            position: 'absolute',
            right: '-37px', top: '50%',
            transform: 'translateY(-50%)',
            zIndex: 10,
          }}>
            {renderHandWithStatus(east, '东', { width: 'auto', height: 'auto', noInfo: true, orientation: 'vertical', popDirection: 'left' })}
          </Box>
          {/* 东家信息条：中心面板右侧，旋转90° */}
          <Box sx={{
            position: 'absolute',
            top: '50%',
            left: `calc(50% + ${centerBoxWidth / 2}px + 3px + ${infoBarHeight / 2}px)`,
            transform: 'translate(-50%, -50%) rotate(90deg)',
            transformOrigin: 'center center',
            zIndex: 100,
            whiteSpace: 'nowrap',
          }}>
            <InfoBar position="东" />
          </Box>

          {/* 独立手牌输入框 + 未知控件 */}
          {renderIndependentHandInput('北')}
          {renderIndependentHandInput('南')}
          {renderIndependentHandInput('西')}
          {renderIndependentHandInput('东')}
          {renderIndependentUnknown('北')}
          {renderIndependentUnknown('南')}
          {renderIndependentUnknown('西')}
          {renderIndependentUnknown('东')}
        </Box>
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

      {/* 牌桌右下角：墩数统计 + 得分 */}
      {showPlayPanel && playState?.contract && (() => {
        const contract = playState.contract
        const declarerTricks = playState.declarer_tricks || 0
        const defenderTricks = playState.defender_tricks || 0
        const isComplete = playState.phase === 'complete'
        let finalScores = null
        if (isComplete && contract?.level) {
          finalScores = {
            nonVul: calcScore(contract.level, contract.suit || 'NT', contract.doubled || false, contract.redoubled || false, declarerTricks, false),
            vul: calcScore(contract.level, contract.suit || 'NT', contract.doubled || false, contract.redoubled || false, declarerTricks, true),
          }
        }
        const bottomStyle = isMobile ? { bottom: 8, right: 8 } : { bottom: 12, right: 12 }
        return (
          <Box sx={{
            position: 'absolute',
            zIndex: 20,
            ...bottomStyle,
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            alignItems: 'flex-end',
          }}>
            <Box sx={{
              display: 'flex',
              gap: 0.75,
              alignItems: 'center',
              bgcolor: isDark ? 'rgba(17,24,39,0.88)' : 'rgba(255,255,255,0.9)',
              backdropFilter: 'blur(10px)',
              borderRadius: 1.5,
              px: 1,
              py: 0.5,
              border: '1px solid',
              borderColor: 'divider',
              boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
            }}>
              <Typography component="span" variant="caption" sx={{ fontSize: '0.7rem', color: 'text.secondary' }}>
                庄 <strong style={{ color: theme.palette.primary.main }}>{declarerTricks}</strong>
              </Typography>
              <Typography component="span" variant="caption" sx={{ fontSize: '0.7rem', color: 'text.secondary' }}>
                防 <strong style={{ color: theme.palette.warning.main }}>{defenderTricks}</strong>
              </Typography>
              <Typography component="span" variant="caption" sx={{ fontSize: '0.7rem', color: 'text.secondary' }}>
                {isComplete && declarerTricks !== undefined && contract.tricks_needed
                  ? (declarerTricks >= contract.tricks_needed
                      ? <>超 <strong style={{ color: '#2e7d32' }}>{declarerTricks - contract.tricks_needed}</strong></>
                      : <>宕 <strong style={{ color: '#c62828' }}>{contract.tricks_needed - declarerTricks}</strong></>)
                  : <>需 <strong>{contract.tricks_needed || '?'}</strong></>
                }
              </Typography>
            </Box>
            {isComplete && finalScores && (
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <Chip
                  label={`无 ${finalScores.nonVul >= 0 ? '+' : ''}${finalScores.nonVul}`}
                  size="small"
                  sx={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    height: 22,
                    bgcolor: isDark ? 'rgba(76,175,80,0.2)' : '#e8f5e9',
                    color: finalScores.nonVul >= 0 ? '#2e7d32' : '#c62828',
                    backdropFilter: 'blur(8px)',
                  }}
                />
                <Chip
                  label={`有 ${finalScores.vul >= 0 ? '+' : ''}${finalScores.vul}`}
                  size="small"
                  sx={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    height: 22,
                    bgcolor: isDark ? 'rgba(255,152,0,0.2)' : '#fff3e0',
                    color: finalScores.vul >= 0 ? '#e65100' : '#c62828',
                    backdropFilter: 'blur(8px)',
                  }}
                />
              </Box>
            )}
          </Box>
        )
      })()}

      {/* 人类无手牌时通过花色+牌点选择出牌（类似叫牌面板） */}
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

        // 计算不可选的牌：已出的牌 + 其他位置可见手牌中的牌
        const playedSet = getPlayedCardsSet() || new Set()
        const otherPositions = ['南', '西', '北', '东'].filter(p => p !== cp)
        const takenSet = new Set(playedSet)
        const suitSymbols = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }
        for (const pos of otherPositions) {
          const h = hands?.[pos]
          if (!h) continue
          for (const [suitKey, symbol] of Object.entries(suitSymbols)) {
            const ranks = h[suitKey]
            if (!ranks || ranks === '-') continue
            for (const r of ranks) takenSet.add(symbol + r.toUpperCase())
          }
        }
        // 跟花色规则：人类位置无手牌数据，无法判断是否有该花色，仅在标题提示
        const ledSuit = playState.current_trick?.cards?.[0]?.[1]?.suit || null

        const SUIT_ROWS = [
          { symbol: '♠', color: isDark ? '#cbd5e1' : '#1a1a2e', key: 'spades' },
          { symbol: '♥', color: '#dc2626', key: 'hearts' },
          { symbol: '♦', color: '#7c3aed', key: 'diamonds' },
          { symbol: '♣', color: isDark ? '#cbd5e1' : '#1a1a2e', key: 'clubs' },
        ]
        const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        const rankDisplay = (r) => r === 'T' ? '10' : r

        const handlePick = (symbol, rank) => {
          onManualPlay?.(cp, symbol + rank)
        }

        const posStyle = playPanelPos
          ? { left: playPanelPos.x, top: playPanelPos.y }
          : { bottom: 16, left: '50%', transform: 'translateX(-50%)' }

        const onMouseDown = (e) => {
          if (e.button !== 0) return
          setDragging(true)
          const panelEl = e.currentTarget.parentElement
          const rect = panelEl.getBoundingClientRect()
          setDragStart({ x: e.clientX - rect.left, y: e.clientY - rect.top })
        }

        const panelContent = (
          <Box sx={{
            position: 'fixed', zIndex: 9999, ...posStyle,
            bgcolor: isDark ? 'rgba(17,24,39,0.92)' : 'rgba(255,255,255,0.92)',
            backdropFilter: 'blur(12px)',
            borderRadius: 2, p: 1,
            border: '1px solid', borderColor: 'divider',
            boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
            display: 'flex', flexDirection: 'column', gap: 0.4,
            maxWidth: isMobile ? '96vw' : 'auto',
            cursor: dragging ? 'grabbing' : 'auto',
          }}>
            <Box
              sx={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.3, px: 0.5,
                cursor: 'grab', userSelect: 'none',
                '&:active': { cursor: 'grabbing' },
              }}
              onMouseDown={onMouseDown}
            >
              <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: isDark ? '#e2e8f0' : '#333' }}>
                {cp}家 出牌{ledSuit ? ` (跟${ledSuit})` : ' (首攻)'}
                {'  '}<span style={{ fontSize: '0.6rem', fontWeight: 400, color: isDark ? '#94a3b8' : '#aaa' }}>拖拽移动</span>
              </Typography>
              <Typography sx={{ fontSize: '0.65rem', color: isDark ? '#94a3b8' : '#888' }}>
                灰色=已出/他手
              </Typography>
            </Box>
            {SUIT_ROWS.map(({ symbol, color }) => {
              const isLedSuit = ledSuit === symbol
              return (
                <Box key={symbol} sx={{
                  display: 'flex', alignItems: 'center', gap: 0.3,
                  bgcolor: isLedSuit ? (isDark ? 'rgba(99,102,241,0.15)' : 'rgba(99,102,241,0.08)') : 'transparent',
                  borderRadius: 1, px: 0.3, py: 0.15,
                  border: isLedSuit ? `1px solid ${isDark ? 'rgba(129,140,248,0.4)' : 'rgba(99,102,241,0.3)'}` : '1px solid transparent',
                }}>
                  <Box sx={{
                    width: 20, minWidth: 20, height: 24,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color, fontSize: '0.95rem', fontWeight: 700,
                  }}>{symbol}</Box>
                  <Box sx={{ display: 'flex', gap: 0.25, flexWrap: 'nowrap' }}>
                    {RANKS.map((rank) => {
                      const cardKey = symbol + rank
                      const isTaken = takenSet.has(cardKey)
                      return (
                        <Button
                          key={rank}
                          variant="outlined"
                          size="small"
                          disabled={isTaken}
                          onClick={() => handlePick(symbol, rank)}
                          sx={{
                            minWidth: 0, width: isMobile ? 22 : 26, height: 24, p: 0,
                            fontSize: '0.7rem', fontWeight: 700,
                            color: isTaken ? (isDark ? '#475569' : '#aaa') : color,
                            bgcolor: isTaken
                              ? (isDark ? 'rgba(100,116,139,0.08)' : 'rgba(148,163,184,0.1)')
                              : (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.6)'),
                            borderColor: isTaken
                              ? (isDark ? 'rgba(100,116,139,0.2)' : 'rgba(148,163,184,0.25)')
                              : (isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)'),
                            '&:hover': isTaken ? {} : {
                              bgcolor: isDark ? 'rgba(99,102,241,0.25)' : 'rgba(99,102,241,0.15)',
                              borderColor: '#6366f1',
                              transform: 'translateY(-1px)',
                            },
                            cursor: isTaken ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {rankDisplay(rank)}
                        </Button>
                      )
                    })}
                  </Box>
                </Box>
              )
            })}
          </Box>
        )
        return ReactDOM.createPortal(panelContent, document.body)
      })()}

      {renderHandPickerPanel()}
    </Box>
  );
}

export default CardTable;
