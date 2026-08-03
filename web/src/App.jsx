import { useEffect, useRef, useCallback, useMemo, useState } from 'react'
import {
  Container,
  Typography,
  Button,
  Box,
  Paper,
  Alert,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
  Switch,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Divider,
  Badge,
  ToggleButtonGroup,
  ToggleButton,
  useTheme,
  useMediaQuery
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import HistoryIcon from '@mui/icons-material/History'
import { aiBid, analyzeBidding, humanBid, getOutputFormats, analyzeContract, doubleDummyAnalysis, playInit, playCard, aiPlay, getPlayState, updatePlayPlayerRoles, undoPlay, setPlayHand, getDDHints, getDDHintsReview, customDeal as apiCustomDeal } from './services/api'
import HandDisplay from './components/HandDisplay'
import Header from './components/layout/Header'
import BiddingDetailPanel from './components/BiddingDetailPanel'
import CardTablePanel from './components/CardTablePanel'
import MainTableArea from './components/MainTableArea'
import SettingsPanel from './components/SettingsPanel'
import PlayPanel from './components/PlayPanel'
import PlayDetailPanel from './components/PlayDetailPanel'
import HistoryDialog from './components/HistoryDialog'
import useBridgeRecords from './hooks/useBridgeRecords'
import useModelSettings from './hooks/useModelSettings'
import useDealing from './hooks/useDealing'
import { getPartnerPosition, BRIDGE_POSITIONS } from './utils/position'
import { validateHands, validateBidding } from './utils/validation'
import { formatElapsedTime } from './utils/biddingUtils'
import './App.css'

/** 确保手牌每门花色按 A→2 排序，并计算 HCP */
const ensureSortedHands = (hands) => {
  if (!hands || typeof hands !== 'object') return hands
  const rankOrder = 'AKQJT98765432'
  const sortSuit = (s) => {
    if (!s || typeof s !== 'string') return ''
    return s.split('').sort((a, b) => rankOrder.indexOf(a) - rankOrder.indexOf(b)).join('')
  }
  const calcHCP = (cards) => {
    let h = 0
    for (const c of cards.toUpperCase()) {
      if (c === 'A') h += 4
      else if (c === 'K') h += 3
      else if (c === 'Q') h += 2
      else if (c === 'J') h += 1
    }
    return h
  }
  const suits = ['spades', 'hearts', 'diamonds', 'clubs']
  const result = { ...hands }
  for (const p of Object.keys(result)) {
    const h = result[p]
    if (h && typeof h === 'object') {
      let allCards = ''
      for (const sk of suits) {
        h[sk] = sortSuit(h[sk] || '')
        allCards += h[sk]
      }
      h.hcp = calcHCP(allCards)
    }
  }
  return result
}
import { GameProvider, useGame } from './context/GameContext'
import { BiddingProvider, useBidding } from './context/BiddingContext'
import { PlayProvider, usePlay } from './context/PlayContext'

const BIDDING_DRAFT_KEY = 'bridge_bidding_draft'

function AppShell({ darkMode, onToggleDarkMode }) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  
  const isLoadingRecordRef = useRef(false) // 用于标记是否正在加载历史记录（不触发保存）
  const draftRestoredRef = useRef(false) // 防止重复恢复草稿
  const draftSaveTimerRef = useRef(null) // debounce 叫牌草稿自动保存
  const lastBidTimeRef = useRef(null) // 上一条叫牌记录完成的时间戳，用于计算单次耗时
  const biddingStartTimeRef = useRef(null) // 同步存储叫牌开始时间，避免 React state 异步问题
  const aiCallStartRef = useRef(null) // AI 调用开始时间，用于准确计算单次 AI 耗时
  // ── Game 域状态（迁入 GameContext）──
  const {
    hands, setHands,
    loading, setLoading,
    aiThinking, setAiThinking,
    error, setError,
    warning, setWarning,
    gameMode, setGameMode,
    dealer, setDealer,
    vulnerability, setVulnerability,
    practiceDirection, setPracticeDirection,
    positionRoles, setPositionRoles,
    setShowPartnerHand,
    setShowOpponentHands,
    useFallback, setUseFallback,
    dealMode, setDealMode,
    showSettings, setShowSettings,
    dealSystem, setDealSystem,
    fallbackModel,
    playModel,
    apiStatus,
    currentRecordId, setCurrentRecordId,
    showDraftBanner, setShowDraftBanner,
    customDealOpen, setCustomDealOpen,
    imageDealOpen, setImageDealOpen,
    customDealText, setCustomDealText,
    imagePath, setImagePath,
    imageFile, setImageFile,
    imageOpeningLead, setImageOpeningLead,
    mode, setMode,
    setReadonlyMode,
  } = useGame()

  // 修正手牌/编辑叫牌对话框的校验信息（仅在该对话框内显示）
  const [handsValidationError, setHandsValidationError] = useState([])
  const [handsValidationWarning, setHandsValidationWarning] = useState([])
  const [biddingValidationError, setBiddingValidationError] = useState([])
  const [biddingValidationWarning, setBiddingValidationWarning] = useState([])

  // 将当前手牌转换为自定义牌局文本格式（带花色符号，便于阅读编辑）
  const handsToEditText = (handsObj) => {
    if (!handsObj) return ''
    const order = ['南', '西', '北', '东']
    const suitSymbols = ['♠', '♥', '♦', '♣']
    const suitKeys = ['spades', 'hearts', 'diamonds', 'clubs']
    return order.map(pos => {
      const hand = handsObj[pos]
      if (!hand) return ''
      return suitKeys.map((k, i) => {
        const cards = hand[k] || ''
        return cards ? `${suitSymbols[i]}${cards}` : `${suitSymbols[i]}-`
      }).join(' ')
    }).join('\n')
  }

  // 将叫牌序列转换为编辑文本
  const biddingToEditText = (seq) => {
    if (!seq || seq.length === 0) return ''
    return seq.map(b => `(${b.position})${b.bid}`).join('-')
  }

  // ── Bidding 域状态（迁入 BiddingContext）──
  const {
    biddingSequence, setBiddingSequence,
    currentBidder, setCurrentBidder,
    setBidSuggestion,
    aiBiddingHistory, setAiBiddingHistory,
    currentBiddingPosition, setCurrentBiddingPosition,
            biddingStarted, setBiddingStarted,
    stopBidding, setStopBidding,
    passedAIPositions, setPassedAIPositions,
    biddingStartTime,
    setBiddingTotalTime,
    customBidMeaning, setCustomBidMeaning,
    setSuggestionLoading,
    isBiddingComplete,
    initBiddingState,
    toggleStopBiddingState,
    markBiddingStarted,
    biddingHistory, setBiddingHistory,
    historyIndex, setHistoryIndex,
    showEditBiddingDialog, setShowEditBiddingDialog,
    editBiddingText, setEditBiddingText,
    outputFormats, setOutputFormats,
    setOutputFormatsLoading,
    setAnalyzeLoading,
    setAnalyzeResult,
    setShowDoubleDummy,
    setDoubleDummyResult,
    setDoubleDummyLoading,
  } = useBidding()

  // ── Play 域状态（迁入 PlayContext）──
  const {
    playState, setPlayState,
    playLoading, setPlayLoading,
    showPlayPanel, setShowPlayPanel,
    setShowPlayedCards,
    setPlayCenterView,
    isPlayPaused, setIsPlayPaused,
    setLastCompletedTrick,
    aiPlayHistory, setAiPlayHistory,
    setSelectedPlayRecord,
    setPlayStarted,
    playInitiated, setPlayInitiated,
    loadedPlayRecord, setLoadedPlayRecord,
    reviewCursor, setReviewCursor,
    showDDHints,
    setDDHints,
    setDDHintsLoading,
    contractDialogOpen, setContractDialogOpen,
    contractDialogForm, setContractDialogForm,
    resetOpeningLeadDialogOpen, setResetOpeningLeadDialogOpen,
    resetOpeningLeadValue, setResetOpeningLeadValue,
    directPlayContractInfo, setDirectPlayContractInfo,
    playEngine,
    handlePlayEngineChange,
  } = usePlay()

  // 页面加载时检测是否有未完成的叫牌草稿
  useEffect(() => {
    try {
      const draftStr = localStorage.getItem(BIDDING_DRAFT_KEY)
      if (!draftStr) return
      const draft = JSON.parse(draftStr)
      // 超过 2 小时的草稿视为过期
      if (Date.now() - draft.timestamp > 2 * 60 * 60 * 1000) {
        localStorage.removeItem(BIDDING_DRAFT_KEY)
        return
      }
      setShowDraftBanner(true)
    } catch {
      localStorage.removeItem(BIDDING_DRAFT_KEY)
    }
  }, [])

  // 清除叫牌草稿
  const clearBiddingDraft = () => {
    try {
      localStorage.removeItem(BIDDING_DRAFT_KEY)
    } catch { /* ignore */ }
    setShowDraftBanner(false)
  }

  // 恢复叫牌草稿
  const restoreBiddingDraft = () => {
    try {
      const draftStr = localStorage.getItem(BIDDING_DRAFT_KEY)
      if (!draftStr) return
      const draft = JSON.parse(draftStr)
      draftRestoredRef.current = true
      // 确保草稿手牌经过排序和 HCP 计算（兼容旧版草稿）
      const sortedDraftHands = ensureSortedHands(draft.hands)
      setHands(sortedDraftHands)
      setDealer(draft.dealer)
      setGameMode(draft.gameMode)
      setPositionRoles(draft.positionRoles)
      if (draft.practiceDirection) setPracticeDirection(draft.practiceDirection)
      setDealSystem(draft.dealSystem)
      setDealMode(draft.dealMode)
      setBiddingSequence(draft.biddingSequence)
      setCurrentBidder(draft.currentBidder)
      setAiBiddingHistory(draft.aiBiddingHistory)
      setBiddingHistory(draft.biddingHistory || [])
      setHistoryIndex(draft.historyIndex ?? -1)
      setBiddingStarted(draft.biddingStarted)
      setStopBidding(draft.stopBidding)
      setPassedAIPositions(new Set(draft.passedAIPositions || []))
      setShowDraftBanner(false)
    } catch (e) {
      console.warn('恢复叫牌草稿失败:', e)
      clearBiddingDraft()
    }
  }
  // 游戏设置状态已迁入 GameContext（useGame）
  // Bidding 域输出格式/分析状态已迁入 BiddingContext（useBidding）
  
  
  // 牌局记录管理（叫牌+打牌统一存储）
  const {
    records: bridgeRecords, setRecords: setBridgeRecords,
    historyDialogOpen, setHistoryDialogOpen,
    loadRecords: loadBridgeRecords,
    saveRecord: saveBridgeRecord,
    deleteRecord: deleteBridgeRecord,
    deleteRecords: deleteBridgeRecords,
    updateRecordNote,
    importRecords,
  } = useBridgeRecords()
  // 牌局对话框状态已迁入 GameContext
  // 双明手分析状态已迁入 BiddingContext
  // Play 域状态已迁入 PlayContext（usePlay）

  const prevTricksCountRef = useRef(0) // 用于检测一墩完成
  const playStateRef = useRef(playState)
  const aiPlayHistoryRef = useRef(aiPlayHistory)
  const abortControllerRef = useRef(null)
  useEffect(() => { playStateRef.current = playState }, [playState])
  useEffect(() => { aiPlayHistoryRef.current = aiPlayHistory }, [aiPlayHistory])

  // ── 模型配置 hook（备用模型/打牌模型/DD采样/API状态/JF重载）──
  const {
    ddSampleCount,
    handleDDSampleCountChange,
    ddParticles, ddParticlesRange,
    mctsParticles, mctsParticlesRange,
    alphaMuParticles, alphaMuParticlesRange,
    handleParticleChange,
    handleFallbackModelChange,
    handlePlayModelChange,
    checkApiStatus,
    handleReloadJF,
    parseModelValue,
    availableModels,
  } = useModelSettings()

  // 检查API状态 + 加载历史记录
  useEffect(() => {
    checkApiStatus()
    loadBridgeRecords()
  }, [checkApiStatus, loadBridgeRecords])



  // Strip redundant playState fields already in board before storing
  const stripPlayState = (ps) => {
    if (!ps) return null
    const { contract: _c, bidding_sequence: _b, player_roles: _p, dummy: _d, is_human_turn: _h, ...rest } = ps
    return rest
  }

  // 存盘时裁剪：去掉 prompt（巨大文本不显示），保留 reasoning/follow_up/full_output
  const trimPlayHistory = (h) => {
    if (!h) return []
    return h.map(({ prompt, ...rest }) => rest)
  }
  // 裁剪叫牌历史：去掉 hand/biddingSequence（board已存），保留完整 result（含 LLM 输出）
  const trimBiddingHistory = (h) => {
    if (!h) return []
    return h.map(({ hand: _h, biddingSequence: _bs, ...rest }) => ({
      ...rest,
      hand: _h,
    }))
  }

  // 生成叫牌时间戳：累计时间 (单次耗时)
  // individualMs: 单次耗时毫秒，AI 调用在 await 后直接传入，避免 React 渲染延迟
  const makeBidTimestamp = (individualMs = null) => {
    const now = Date.now()
    const start = biddingStartTimeRef.current
    if (!start) {
      console.warn('[makeBidTimestamp] biddingStartTimeRef is falsy, state=', biddingStartTime)
    }
    const effectiveStart = start || biddingStartTime || now
    const cumulative = formatElapsedTime(now - effectiveStart)
    let individual = ''
    // 只有非首个叫品才显示单次耗时（首个叫品没有上一条可参照）
    if (lastBidTimeRef.current) {
      if (individualMs !== null) {
        // AI 调用：用传入的精确耗时
        individual = individualMs >= 1000 ? `${Math.round(individualMs / 1000)}s` : `${individualMs}ms`
      } else {
        // 人类叫牌：距上一条记录的时间差
        const ms = now - lastBidTimeRef.current
        individual = ms >= 1000 ? `${Math.round(ms / 1000)}s` : `${ms}ms`
      }
    }
    lastBidTimeRef.current = now
    return individual ? `${cumulative} (+${individual})` : cumulative
  }


  // 加载历史记录到牌桌
  const loadRecordToTable = (record) => {
    isLoadingRecordRef.current = true
    // 设置当前记录ID，用于后续覆盖保存
    setCurrentRecordId(record.id)
    // 兼容新旧格式
    const board = record.board || record
    const bidding = record.bidding || record
    // 有打牌记录 → 从 tricks 重建完整四家手牌，完成后不区分来源
    let resolvedHands = board.hands || record.hands || {}
    // 从打牌记录 tricks 重建完整四家手牌
    const playTricks = record.play?.tricks
    const hasPlayState = !!(playTricks && playTricks.length > 0)
    if (hasPlayState) {
      const ALL_POS = ['北', '东', '南', '西']
      const playedByPos = Object.fromEntries(ALL_POS.map(p => [p, []]))
      for (const t of playTricks) {
        for (const [p, c] of (t.cards || [])) playedByPos[p].push(c)
      }
      const sm = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
      resolvedHands = {}
      for (const p of ALL_POS) {
        const hand = { spades: '', hearts: '', diamonds: '', clubs: '' }
        const seen = new Set()
        for (const c of (playedByPos[p] || [])) {
          const key = `${c.suit}${c.rank}`
          if (!seen.has(key)) { seen.add(key); const sk = sm[c.suit]; if (sk) hand[sk] += c.rank }
        }
        resolvedHands[p] = hand
      }
    }
    setHands(ensureSortedHands(resolvedHands))
    setBiddingSequence(board.bidding_sequence || record.biddingSequence || [])
    setDealer(board.dealer || record.dealer)
    setImageOpeningLead(board.opening_lead || null)
    // 有打牌记录时不恢复 gameMode，完成后与发牌练习走同样路径
    if (!hasPlayState && (board.game_mode || record.gameMode)) {
      setGameMode(board.game_mode || record.gameMode)
    }
    if (board.practice_direction) {
      setPracticeDirection(board.practice_direction)
    }
    if (board.position_roles) {
      setPositionRoles(board.position_roles)
    } else if (board.human_position || record.humanPosition) {
      // 兼容旧格式：从 human_position 转换
      const hp = board.human_position || record.humanPosition
      const positions = ['北', '南', '东', '西']
      const humans = Array.isArray(hp) ? hp : [hp]
      const newRoles = Object.fromEntries(positions.map(p => [p, humans.includes(p) ? 'human' : 'ai']))
      setPositionRoles(newRoles)
    }
    setAiBiddingHistory(bidding.ai_bidding_history || record.aiBiddingHistory || [])
    if (bidding.deal_system || record.dealSystem) {
      setDealSystem(bidding.deal_system || record.dealSystem)
    }
    setBiddingStarted(true)
    setStopBidding(true) // 加载历史记录后允许切换发牌人
    setShowPartnerHand(true)
    setShowOpponentHands(true)
    setHistoryDialogOpen(false)
    setOutputFormats(null) // 重置输出格式
    setShowDoubleDummy(false) // 切换到显示叫牌过程
    setDoubleDummyResult(null) // 清除双明手结果
    // 清除上一副牌残留的打牌状态，避免桌面显示旧牌
    setLastCompletedTrick(null)
    setReviewCursor(null)
    setSelectedPlayRecord(null)
    // 预加载打牌数据
    if (record.play && record.play.tricks && record.play.tricks.length > 0) {
      // 完整记录含 tricks 数组
      const contractFromRecord = board.contract
      const suitMap = { S: '♠', H: '♥', D: '♦', C: '♣', NT: 'NT' }
      const partnerMap = { '北': '南', '南': '北', '东': '西', '西': '东' }

      const contract = contractFromRecord ? {
        level: contractFromRecord.level,
        suit: suitMap[contractFromRecord.suit] || contractFromRecord.suit || 'NT',
        declarer: contractFromRecord.declarer,
        doubled: contractFromRecord.isDouble || false,
        redoubled: contractFromRecord.isRedouble || false,
        tricks_needed: (contractFromRecord.level || 0) + 6,
      } : null

      const restoredPlayState = {
        contract,
        hands: { '北': [], '南': [], '东': [], '西': [] },
        dummy: contract ? partnerMap[contract.declarer] : null,
        player_roles: board.player_roles || {},
        tricks: record.play.tricks,
        current_trick: { cards: [], leader: null, trump: contract?.suit || null },
        current_player: null,
        lead_player: null,
        declarer_tricks: record.play.declarer_tricks || 0,
        defender_tricks: record.play.defender_tricks || 0,
        phase: 'complete',
        is_human_turn: false,
      }

      setLoadedPlayRecord({
        playState: restoredPlayState,
        aiPlayHistory: record.play.ai_play_history || [],
      })
    }
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setIsPlayPaused(false)

    // 判断手牌齐全：四家各13张 → 恢复4AI可操作；不齐全 → 只读
    // 用重建后的 resolvedHands（含从 tricks 重建的手牌）
    const allComplete = resolvedHands && ['南','北','东','西'].every(pos => {
      const h = resolvedHands[pos]
      if (!h) return false
      const total = (h.spades?.length || 0) + (h.hearts?.length || 0) + (h.diamonds?.length || 0) + (h.clubs?.length || 0)
      return total === 13
    })
    if (allComplete) {
      setPositionRoles({ '南': 'ai', '北': 'ai', '东': 'ai', '西': 'ai' })
      setReadonlyMode(false)
    } else {
      // 手牌不全时不锁定界面：模拟实战中人类手牌未知是正常的，
      // 用户应能重新叫牌、编辑叫牌、切换角色、补输手牌
      setReadonlyMode(false)
    }

    // 加载历史记录后获取更多输出格式
    if ((board.hands || record.hands) && (board.bidding_sequence || record.biddingSequence) && (board.bidding_sequence || record.biddingSequence).length > 0) {
      // 延迟调用，确保状态已更新
      setTimeout(() => {
        fetchOutputFormatsForRecord(record)
        isLoadingRecordRef.current = false
      }, 100)
    } else {
      isLoadingRecordRef.current = false
    }
  }
  
  // 为历史记录获取输出格式
  const fetchOutputFormatsForRecord = async (record) => {
    // 兼容新旧格式
    const hands = record.board?.hands || record.hands
    const biddingSequence = record.board?.bidding_sequence || record.biddingSequence
    const dealer = record.board?.dealer || record.dealer
    
    if (!hands || !biddingSequence || biddingSequence.length === 0) return
    
    setOutputFormatsLoading(true)
    try {
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      console.log('[DEBUG] 加载历史记录获取输出格式, biddingStr:', biddingStr, 'dealer:', dealer)
      const result = await getOutputFormats(hands, biddingStr, dealer, gameMode, positionRoles, imageOpeningLead)
      console.log('[DEBUG] 输出格式结果:', result)
      setOutputFormats(result)
    } catch (err) {
      console.error('获取输出格式失败:', err)
    } finally {
      setOutputFormatsLoading(false)
    }
  }

  // 叫牌回退功能
  const saveBiddingSnapshot = useCallback(() => {
    const snapshot = {
      biddingSequence: [...biddingSequence],
      currentBidder,
      aiBiddingHistory: [...aiBiddingHistory],
    }
    const newHistory = historyIndex >= 0 
      ? biddingHistory.slice(0, historyIndex + 1) 
      : biddingHistory
    setBiddingHistory([...newHistory, snapshot])
    setHistoryIndex(newHistory.length)
  }, [biddingSequence, currentBidder, aiBiddingHistory, biddingHistory, historyIndex])

  const undoBidding = useCallback(() => {
    if (historyIndex > 0) {
      const snapshot = biddingHistory[historyIndex - 1]
      setBiddingSequence(snapshot.biddingSequence)
      setCurrentBidder(snapshot.currentBidder)
      // snapshot.aiBiddingHistory 可能比 biddingSequence 少一条（React 批处理时序问题），
      // 用 biddingSequence 长度截断 aiBiddingHistory 保证两者一致
      const targetLen = snapshot.biddingSequence.length
      setAiBiddingHistory(prev => prev.slice(0, targetLen))
      setHistoryIndex(historyIndex - 1)
      setBidSuggestion(null)
    }
  }, [biddingHistory, historyIndex])

  // 只有停止叫牌后才能撤销，且AI不在加载中（包括AI叫牌和获取叫品含义）
  const showUndo = stopBidding && historyIndex > 0
  const canUndo = !aiThinking && !currentBiddingPosition

  // 判断是否可以保存进度（叫牌模式）
  const canSaveProgress = hands && !showPlayPanel && biddingStarted && !isBiddingComplete() && stopBidding

  // 打牌模式下是否可以保存
  const playCanSave = showPlayPanel && playState && playState.phase !== 'complete' && isPlayPaused

  // 手动保存进度（使用ref避免playState/aiPlayHistory变化导致回调重建）
  const handleSaveProgress = useCallback(() => {
    if (!hands || !biddingSequence || biddingSequence.length === 0) return
    const ps = playStateRef.current
    const aph = aiPlayHistoryRef.current

    // 打牌进行中：保存打牌状态
    if (showPlayPanel && ps && ps.phase !== 'complete') {
      // 从第一墩第一张牌提取首攻（如果 imageOpeningLead 为空）
      let saveOpeningLead = imageOpeningLead || undefined
      if (!saveOpeningLead && ps.tricks?.length > 0) {
        const firstTrick = ps.tricks[0]
        if (firstTrick.cards?.length > 0) {
          const [leadPos, leadCard] = firstTrick.cards[0]
          saveOpeningLead = `${leadPos}:${leadCard.suit}${leadCard.rank}`
        }
      }
      const record = {
        id: Date.now().toString(),
        timestamp: new Date().toLocaleString(),
        type: 'play_in_progress',
        sourceRecordId: currentRecordId || undefined,
        board: {
          hands: hands,
          bidding_sequence: biddingSequence,
          contract: ps.contract ? {
            level: ps.contract.level,
            suit: ps.contract.suit,
            declarer: ps.contract.declarer,
            isDouble: ps.contract.is_double,
            isRedouble: ps.contract.is_redouble,
          } : null,
          dealer: dealer,
          game_mode: gameMode,
          practice_direction: practiceDirection,
          position_roles: positionRoles,
          player_roles: positionRoles,
          opening_lead: saveOpeningLead,
        },
        bidding: {
          ai_bidding_history: trimBiddingHistory(aiBiddingHistory),
          deal_system: dealSystem,
        },
        play: {
          state: stripPlayState(ps),
          ai_play_history: trimPlayHistory(aph),
        },
        note: ''
      }
      saveBridgeRecord(record)
      if (!currentRecordId) {
        setCurrentRecordId(record.id)
      }
      return
    }

    // 叫牌进行中：保存叫牌状态
    const record = {
      id: Date.now().toString(),
      timestamp: new Date().toLocaleString(),
      type: 'bidding_in_progress',
      sourceRecordId: currentRecordId || undefined,
      board: {
        hands: hands,
        bidding_sequence: biddingSequence,
        contract: null,
        dealer: dealer,
        game_mode: gameMode,
        practice_direction: practiceDirection,
        position_roles: positionRoles,
        opening_lead: imageOpeningLead || undefined,
      },
      bidding: {
        ai_bidding_history: trimBiddingHistory(aiBiddingHistory),
        deal_system: dealSystem,
      },
      play: null,
      note: ''
    }
    saveBridgeRecord(record)
    if (!currentRecordId) {
      setCurrentRecordId(record.id)
    }
  }, [hands, biddingSequence, dealer, gameMode, practiceDirection, positionRoles, aiBiddingHistory, dealSystem, currentRecordId, showPlayPanel])

  // ── 发牌流程 hook（发牌/自定义牌局/图片识别/截屏识别/清除手牌）──
  const {
    handleDeal,
    handleCustomDeal,
    handleImageDeal,
    handleScreenshotDeal,
    handleSingleHandScreenshot,
    clearAllHands,
    parseBiddingSequenceStr,
    screenshotCancelledRef,
  } = useDealing({ clearBiddingDraft })

  // 截屏识别需要关闭设置面板
  const onScreenshotDeal = () => handleScreenshotDeal({ setShowSettings })

  // 开始叫牌
  const startBidding = () => {
    if (hands) {
      // 检查AI位置是否都有手牌
      const aiPositions = Object.entries(positionRoles)
        .filter(([, role]) => role === 'ai')
        .map(([pos]) => pos)
      
      for (const pos of aiPositions) {
        const hand = hands[pos]
        if (!hand || (!hand.spades && !hand.hearts && !hand.diamonds && !hand.clubs)) {
          setError(`${pos}家(AI)没有手牌，请先输入手牌`)
          return
        }
      }
      
      // 重置叫牌序列并标记开始
      setBiddingSequence([])
      setCurrentBidder(dealer)
      markBiddingStarted()
      biddingStartTimeRef.current = Date.now() // 同步记录，避免 React state 延迟
      setAiBiddingHistory([])
      setStopBidding(false)
      setPassedAIPositions(new Set())
      setBiddingTotalTime(null)
      setError(null)
      lastBidTimeRef.current = null
      // 重置回退历史并保存初始快照
      const initialSnapshot = {
        biddingSequence: [],
        currentBidder: dealer,
        aiBiddingHistory: [],
      }
      setBiddingHistory([initialSnapshot])
      setHistoryIndex(0)
    }
  }

  // 重新叫牌（保持当前牌局）
  const resetBidding = () => {
    clearBiddingDraft()
    initBiddingState(dealer)
    setBiddingHistory([])
    setHistoryIndex(-1)
    setLoadedPlayRecord(null)
    setCurrentRecordId(null)
    lastBidTimeRef.current = null
  }

  // 清除所有手牌已迁入 useDealing hook

  const handleModeChange = (newMode) => {
    if (newMode !== mode) {
      setMode(newMode)
      clearAllHands()
      // 切到发牌练习：全部AI；切到模拟实战：默认3人+1AI
      if (newMode === 'practice') {
        setPositionRoles({ '南': 'ai', '北': 'ai', '东': 'ai', '西': 'ai' })
      } else {
        setPositionRoles({ '南': 'ai', '北': 'human', '东': 'human', '西': 'human' })
      }
    }
  }

  const handleDealerChange = useCallback((pos) => {
    setDealer(pos)
    // 双人模式：发牌人切换到对方阵营时自动更新练习方向，重置手牌可见性
    if (gameMode === 'pair') {
      const newDirection = ['南', '北'].includes(pos) ? 'NS' : 'EW'
      if (newDirection !== practiceDirection) {
        setPracticeDirection(newDirection)
      }
      setShowPartnerHand(false)
      setShowOpponentHands(false)
    }
    setCurrentBidder(pos)
    setBiddingStarted(false)
    setStopBidding(false)
    setBiddingSequence([])
    setAiBiddingHistory([])
    setPassedAIPositions(new Set())
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    
    setIsPlayPaused(false)
    setLoadedPlayRecord(null)
  }, [gameMode, practiceDirection])

  // 双人模式：练习方向改变时，同步发牌人（发牌人必须在练习方阵营内）
  useEffect(() => {
    if (gameMode === 'pair' && !biddingStarted) {
      const nsDealers = ['南', '北']
      const ewDealers = ['东', '西']
      const pairDealers = practiceDirection === 'NS' ? nsDealers : ewDealers
      if (!pairDealers.includes(dealer)) {
        setDealer(pairDealers[0])
        setCurrentBidder(pairDealers[0])
      }
    }
  }, [practiceDirection, gameMode, dealer, biddingStarted])

  // 切换停止/继续叫牌
  const toggleStopBidding = () => {
    toggleStopBiddingState()
  }

  // 添加叫牌
  const addBid = async (bid) => {
    // 花色符号→字母规范化（统一显示为字母格式）
    const suitSymbolToLetter = { '♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C' }
    bid = bid.replace(/[♠♥♦♣]/g, sym => suitSymbolToLetter[sym] || sym)
    const isCurrentHuman = positionRoles && positionRoles[currentBidder] === 'human'
    // 人类叫牌后，立即标记叫牌已开始（在currentBidder更新之前）
    if (isCurrentHuman && !biddingStarted) {
      setBiddingStarted(true)
    }
    
    // 人类叫牌时，保存叫牌记录
    if (isCurrentHuman) {
      // 用于显示的字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + (biddingSequence.length > 0 ? '-' : '')
      
      // 如果用户输入了自定义叫牌含义，直接使用，不调用API
      if (customBidMeaning.trim()) {
        setAiBiddingHistory(prev => [...prev, {
          position: currentBidder,
          hand: hands[currentBidder],
          biddingSequence: biddingStr,
          result: { bid: bid, meaning: customBidMeaning.trim() },
          timestamp: makeBidTimestamp()
        }])
        setCustomBidMeaning('') // 清空输入框
      } else {
        // 没有自定义含义，调用API获取（传递数组，后端处理格式）
        setCurrentBiddingPosition(currentBidder)
        try {
          const bidHistory = aiBiddingHistory.map(record => {
            const bidPrefix = `${record.result.bid}：`
            const meaning = record.result.meaning?.startsWith(bidPrefix)
              ? record.result.meaning.slice(bidPrefix.length)
              : (record.result.meaning || '')
            return `(${record.position})${record.result.bid}：${meaning}`
          }).join('\n')
          const result = await humanBid(biddingSequence, currentBidder, bid, dealSystem, bidHistory)
          
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { 
              bid: result.bid, 
              meaning: result.meaning,
              full_output: result.full_output
            },
            timestamp: makeBidTimestamp()
          }])
        } catch (err) {
          console.error('获取叫品含义失败:', err)
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { 
              bid: bid, 
              meaning: '获取叫品含义失败',
              full_output: {}
            },
            timestamp: makeBidTimestamp()
          }])
        } finally {
          setCurrentBiddingPosition(null)
        }
      }
    }
    
    const newBid = {
      position: currentBidder,
      bid: bid
    }
    const newSequence = [...biddingSequence, newBid]
    
    // 计算下一个叫牌者
    const currentIndex = BRIDGE_POSITIONS.indexOf(currentBidder)
    const nextIndex = (currentIndex + 1) % 4
    const nextBidder = BRIDGE_POSITIONS[nextIndex]

    // 根据游戏模式判断是否需要为对方阵营添加自动pass
    if (gameMode === 'pair') {
      // 双人模式：南北 vs 东西，对方自动pass
      const humanPair = practiceDirection === 'NS' ? ['南', '北'] : ['东', '西']
      const isHumanTeam = humanPair.includes(currentBidder)
      const isNextHumanTeam = humanPair.includes(nextBidder)
      
      if (isHumanTeam !== isNextHumanTeam) {
        // 下一个是对方阵营，自动pass — 记录到 aiBiddingHistory
        const passBid = {
          position: nextBidder,
          bid: 'pass'
        }
        newSequence.push(passBid)
        const passBiddingStr = newSequence.map(b => `(${b.position})${b.bid}`).join('-')
        const autoPassRecord = {
          position: nextBidder,
          hand: hands[nextBidder],
          biddingSequence: passBiddingStr,
          result: { bid: 'pass', meaning: '双人模式对方自动pass' },
          timestamp: makeBidTimestamp()
        }
        const updatedHistory = [...aiBiddingHistory, autoPassRecord]
        setAiBiddingHistory(updatedHistory)

        // 继续计算下一个
        const nextNextIndex = (nextIndex + 1) % 4
        const nextNextBidder = BRIDGE_POSITIONS[nextNextIndex]

        setBiddingSequence(newSequence)
        setCurrentBidder(nextNextBidder)

        // 保存叫牌快照（双人模式自动pass）
        const snapshotPair = {
          biddingSequence: newSequence,
          currentBidder: nextNextBidder,
          aiBiddingHistory: [...updatedHistory],
        }
        const newHistoryPair = historyIndex >= 0 
          ? biddingHistory.slice(0, historyIndex + 1) 
          : biddingHistory
        setBiddingHistory([...newHistoryPair, snapshotPair])
        setHistoryIndex(newHistoryPair.length)
        
        return
      }
    }

    setBiddingSequence(newSequence)
    setCurrentBidder(nextBidder)
    
    // 保存叫牌快照
    const snapshot = {
      biddingSequence: newSequence,
      currentBidder: nextBidder,
      aiBiddingHistory: [...aiBiddingHistory],
    }
    const newHistory = historyIndex >= 0 
      ? biddingHistory.slice(0, historyIndex + 1) 
      : biddingHistory
    setBiddingHistory([...newHistory, snapshot])
    setHistoryIndex(newHistory.length)
    
    // 四人模式：检查搭档两人是否相继pass（中间只有对方的一次叫牌或pass）
    // 前提：必须已有实质性叫牌（第一个实质性叫牌之前的pass不算）
    if (gameMode === 'four' && bid === 'pass') {
      // 检查是否已有实质性叫牌
      const hasRealBid = biddingSequence.some(b => b.bid !== 'pass')
      if (!hasRealBid) {
        return
      }
      
      // 搭档关系
      const partnerships = { '南': '北', '北': '南', '东': '西', '西': '东' }
      
      // 找到当前叫牌者的搭档
      const partner = partnerships[currentBidder]
      
      // 找到第一个实质性叫牌的位置
      let firstRealBidIndex = -1
      for (let i = 0; i < newSequence.length; i++) {
        if (newSequence[i].bid !== 'pass') {
          firstRealBidIndex = i
          break
        }
      }
      
      // 在叫牌序列中找搭档最近一次pass的位置（必须在第一个实质性叫牌之后）
      let partnerPassIndex = -1
      for (let i = newSequence.length - 2; i >= 0; i--) {
        if (i < firstRealBidIndex) continue  // 跳过第一个实质性叫牌之前的pass
        if (newSequence[i].position === partner && newSequence[i].bid === 'pass') {
          partnerPassIndex = i
          break
        }
      }
      
      // 如果搭档pass过，检查中间是否只有对方的叫牌
      if (partnerPassIndex !== -1) {
        // 从搭档pass到当前pass，中间应该只有一次叫牌（对方的）
        const bidsBetween = newSequence.slice(partnerPassIndex + 1, -1)
        if (bidsBetween.length === 1) {
          const middleBid = bidsBetween[0]
          // 检查中间的叫牌是否来自对方
          if (partnerships[middleBid.position] !== partner) {
            // 相继pass成立，标记需要自动pass的AI位置
            const currentIsAI = positionRoles[currentBidder] === 'ai'
            const partnerIsAI = positionRoles[partner] === 'ai'
            
            const positionsToMark = []
            if (currentIsAI) {
              positionsToMark.push(currentBidder)
            }
            if (partnerIsAI) {
              positionsToMark.push(partner)
            }
            
            if (positionsToMark.length > 0) {
              console.log(`搭档${currentBidder}和${partner}相继pass，AI位置${positionsToMark.join('、')}后续自动pass`)
              setPassedAIPositions(prev => {
                const newSet = new Set(prev)
                positionsToMark.forEach(pos => newSet.add(pos))
                return newSet
              })
            }
          }
        }
      }
    }
  }

  // 检查AI位置是否需要自动pass
  const shouldAIAutoPass = (position) => {
    return passedAIPositions.has(position)
  }

  // 调用AI叫牌
  const callAIBid = async () => {
    if (!hands || !currentBidder || isBiddingComplete()) return
    
    // 检查是否停止叫牌
    if (stopBidding) return
    
    // 检查是否是人类玩家的回合
    const isHumanTurn = positionRoles && positionRoles[currentBidder] === 'human'
    if (isHumanTurn) return
    
    // 检查AI位置是否需要自动pass
    if (gameMode === 'four' && shouldAIAutoPass(currentBidder)) {
      console.log(`${currentBidder}家因搭档相继pass，自动pass`)
      setAiBiddingHistory(prev => [...prev, {
        position: currentBidder,
        hand: hands[currentBidder],
        biddingSequence: biddingSequence.map(b => `(${b.position})${b.bid}`).join('-'),
        result: { bid: 'pass', meaning: '搭档已相继pass，不再参与叫牌' },
        timestamp: makeBidTimestamp()
      }])
      addBid('pass')
      return
    }
    
    setCurrentBiddingPosition(currentBidder)
    setAiThinking(true)
    try {
      // 用于显示的字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + (biddingSequence.length > 0 ? '-' : '')
      
      // 构建累积的叫牌历史（与终端版格式一致）
      const bidHistory = aiBiddingHistory.map(record => {
        // 含义可能已包含 "叫品：" 前缀（JF匹配），先去重再统一添加
        const bidPrefix = `${record.result.bid}：`
        const meaning = record.result.meaning?.startsWith(bidPrefix)
          ? record.result.meaning.slice(bidPrefix.length)
          : (record.result.meaning || '')
        return `(${record.position})${record.result.bid}：${meaning}`
      }).join('\n')
      
      // 获取当前叫牌者的手牌
      const currentHand = hands[currentBidder]
      
      console.log(`AI叫牌: ${currentBidder}家, 手牌:`, currentHand, '叫牌序列:', biddingStr, '叫牌历史:', bidHistory)
      
      // 传递数组，后端处理格式
      const bm = parseModelValue(fallbackModel)
      const aiCallStart = Date.now()
      const result = await aiBid(currentHand, biddingSequence, currentBidder, dealSystem, bidHistory, useFallback, bm.model, 'deepseek', bm.reasoning)
      const aiCallElapsed = Date.now() - aiCallStart
      
      // 更新useFallback状态
      if (result.use_fallback !== undefined) {
        setUseFallback(result.use_fallback)
      }

      console.log(`AI叫牌结果: ${currentBidder}家, 叫品:`, result.bid, '含义:', result.meaning)

      // 合规性检查失败：后端返回 暂停叫牌 标记时，停止自动叫牌等待用户处理
      if (result.full_output?.暂停叫牌) {
        setStopBidding(true)
        setAiBiddingHistory(prev => [...prev, {
          position: currentBidder,
          hand: currentHand,
          biddingSequence: biddingStr,
          result: { ...result, bid: 'pass', meaning: result.meaning || '[合规性错误] 已暂停叫牌等待处理' },
          timestamp: makeBidTimestamp(aiCallElapsed)
        }])
        addBid('pass')
        return
      }

      // 保存AI叫牌历史记录
      setAiBiddingHistory(prev => [...prev, {
        position: currentBidder,
        hand: currentHand,
        biddingSequence: biddingStr,
        result: result,
        timestamp: makeBidTimestamp(aiCallElapsed)
      }])

      // 添加AI叫牌
      addBid(result.bid)
    } catch (err) {
      console.error('AI叫牌失败:', err)
      // 出错时默认pass，同时记录到aiBiddingHistory
      const errBiddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + (biddingSequence.length > 0 ? '-' : '')
      setAiBiddingHistory(prev => [...prev, {
        position: currentBidder,
        hand: hands[currentBidder],
        biddingSequence: errBiddingStr,
        result: { bid: 'pass', meaning: `AI叫牌异常: ${err.message || err}` },
        timestamp: makeBidTimestamp()
      }])
      addBid('pass')
    } finally {
      setAiThinking(false)
      setCurrentBiddingPosition(null)
    }
  }

  // 获取JF约定片段
  const getJFSuggestion = async () => {
    if (!hands || !currentBidder || isBiddingComplete()) return
    
    setSuggestionLoading(true)
    try {
      // 构建叫牌序列字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      
      // 调用分析API获取JF约定片段
      const result = await analyzeBidding(biddingStr, currentBidder, dealSystem)
      
      setBidSuggestion({
        keyword: result.keyword,
        content: result.content
      })
    } catch (err) {
      console.error('获取JF约定片段失败:', err)
      setBidSuggestion(null)
    } finally {
      setSuggestionLoading(false)
    }
  }

  // 当currentBidder变化时，检查是否需要调用AI叫牌或获取JF约定片段
  useEffect(() => {
    if (!hands || aiThinking) return
    
    // 叫牌已结束，不再处理
    if (isBiddingComplete()) return
    
    // 检查是否需要等待人类叫牌
    const isHumanTurn = positionRoles && positionRoles[currentBidder] === 'human'
    
    // 四人模式下，如果AI位置需要自动pass
    if (gameMode === 'four' && shouldAIAutoPass(currentBidder) && !isHumanTurn) {
      callAIBid()
      return
    }
    
    // 人类玩家回合时，获取JF约定片段并自动切换到叫牌控制面板
    if (isHumanTurn) {
      getJFSuggestion()
    }

    // AI叫牌逻辑
    if (!isHumanTurn && !stopBidding) {
      // AI回合
      const hasHumanPosition = positionRoles && Object.values(positionRoles).some(r => r === 'human')
      if (!hasHumanPosition) {
        // 观察模式：需要点击开始叫牌按钮
        if (biddingStarted) {
          callAIBid()
        }
      } else {
        // 有人类参与
        // 如果人类不是第一个叫牌，需要点击开始叫牌按钮
        // 如果人类是第一个叫牌，人类叫牌后biddingStarted会被设置为true
        if (biddingStarted) {
          callAIBid()
        }
      }
    }
  }, [currentBidder, positionRoles, hands, aiThinking, biddingSequence, biddingStarted, stopBidding, passedAIPositions])

  // 叫牌进度草稿自动保存 —— 每次叫牌序列变化时持久化到 localStorage
  useEffect(() => {
    // 只在叫牌进行中保存，debounce 500ms
    if (!biddingSequence || biddingSequence.length === 0) return
    if (isBiddingComplete()) return

    if (draftSaveTimerRef.current) {
      clearTimeout(draftSaveTimerRef.current)
    }
    draftSaveTimerRef.current = setTimeout(() => {
      const slimHistory = aiBiddingHistory.map(r => ({
        ...r,
        result: { bid: r.result.bid, meaning: r.result.meaning },
      }))
      const draft = {
        hands,
        dealer,
        gameMode,
        practiceDirection,
        positionRoles,
        dealSystem,
        dealMode,
        biddingSequence,
        currentBidder,
        aiBiddingHistory: slimHistory,
        biddingHistory,
        historyIndex,
        biddingStarted,
        stopBidding,
        passedAIPositions: Array.from(passedAIPositions),
        biddingStartTime,
        timestamp: Date.now(),
      }
      try {
        localStorage.setItem(BIDDING_DRAFT_KEY, JSON.stringify(draft))
      } catch (e) {
        console.warn('保存叫牌草稿失败:', e)
      }
    }, 500)

    return () => {
      if (draftSaveTimerRef.current) {
        clearTimeout(draftSaveTimerRef.current)
      }
    }
  }, [biddingSequence, currentBidder, aiBiddingHistory, biddingHistory, historyIndex, biddingStarted, stopBidding, passedAIPositions])






  // 确定最终定约
  const getFinalContract = () => {
    if (!isBiddingComplete() || biddingSequence.length === 0) return null

    // 找到最后一个非pass的叫品
    const nonPassBids = biddingSequence.filter(b => b.bid !== 'pass')
    if (nonPassBids.length === 0) return null

    const lastBid = nonPassBids[nonPassBids.length - 1]
    const bid = lastBid.bid

    // 解析叫品
    let level = 0
    let suit = ''
    let isDouble = false
    let isRedouble = false
    // 定约方位置：对于加倍(X)，定约方是被加倍方而非加倍方
    // 对于再加倍(XX)和普通叫品，定约方就是最后一个叫牌方
    let contractPosition = lastBid.position

    if (bid === 'X') {
      // 找到被加倍的叫品
      const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid !== 'X' && b.bid !== 'XX')
      if (targetBids.length === 0) return null
      const targetBid = targetBids[targetBids.length - 1]
      level = parseInt(targetBid.bid[0])
      suit = targetBid.bid.substring(1)
      isDouble = true
      contractPosition = targetBid.position  // 定约方是被加倍方，不是加倍方
    } else if (bid === 'XX') {
      // 找到被再加倍的叫品
      const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid === 'X')
      if (targetBids.length === 0) return null
      const doubleBid = targetBids[targetBids.length - 1]
      const originalBids = nonPassBids.slice(0, nonPassBids.indexOf(doubleBid)).filter(b => b.bid !== 'X' && b.bid !== 'XX')
      if (originalBids.length === 0) return null
      const originalBid = originalBids[originalBids.length - 1]
      level = parseInt(originalBid.bid[0])
      suit = originalBid.bid.substring(1)
      isDouble = true
      isRedouble = true
      // 再加倍方就是定约方（只有被加倍方才能再加倍），contractPosition 保持 lastBid.position
    } else {
      // 普通叫品
      level = parseInt(bid[0])
      suit = bid.substring(1)
      // contractPosition 保持 lastBid.position
    }

    // 确定定约方（叫牌者所在的一方）
    const partnership = ['南', '北'].includes(contractPosition) ? '南北' : '东西'

    // 确定庄家：定约方中第一个叫出该花色的人
    const partnershipPositions = partnership === '南北' ? ['南', '北'] : ['东', '西']
    let declarer = contractPosition
    for (const bidItem of biddingSequence) {
      if (partnershipPositions.includes(bidItem.position) && bidItem.bid.includes(suit) && bidItem.bid !== 'pass' && bidItem.bid !== 'X' && bidItem.bid !== 'XX') {
        declarer = bidItem.position
        break
      }
    }

    return {
      level,
      suit,
      isDouble,
      isRedouble,
      declarer,
      partnership,
      bid: bid
    }
  }

  const finalContract = useMemo(() => getFinalContract(), [biddingSequence])

  // 叫牌结束时自动保存记录
  useEffect(() => {
    if (isBiddingComplete() && biddingSequence.length > 0 && hands && !isLoadingRecordRef.current) {
      console.log('[自动保存] 叫牌完成，准备保存记录');
      clearBiddingDraft() // 叫牌完成，清除草稿
      // 计算总时间
      if (biddingStartTime) {
        const totalTime = Math.round((Date.now() - biddingStartTime) / 1000)
        setBiddingTotalTime(totalTime)
      }
      
      const finalContract = getFinalContract()
      const record = {
        id: Date.now().toString(),
        timestamp: new Date().toLocaleString(),
        type: 'bidding_complete',
        sourceRecordId: currentRecordId || undefined,
        board: {
          hands: hands,
          bidding_sequence: biddingSequence,
          contract: finalContract,
          dealer: dealer,
          game_mode: gameMode,
          practice_direction: practiceDirection,
          position_roles: positionRoles,
          opening_lead: imageOpeningLead || undefined,
        },
        bidding: {
          ai_bidding_history: trimBiddingHistory(aiBiddingHistory),
          deal_system: dealSystem,
        },
        play: null,
        note: ''
      }
      saveBridgeRecord(record)
      console.log('[自动保存] 叫牌记录已调用保存, id:', record.id)
      // 如果之前没有记录ID，保存后设置当前记录ID
      if (!currentRecordId) {
        setCurrentRecordId(record.id)
      }
      
      // 获取更多输出格式
      fetchOutputFormats()
    }
  }, [biddingSequence, hands, dealer])
  
  // 获取更多输出格式
  const fetchOutputFormats = async () => {
    if (!hands || biddingSequence.length === 0) return
    
    setOutputFormatsLoading(true)
    try {
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      console.log('[DEBUG] 获取输出格式, biddingStr:', biddingStr, 'dealer:', dealer, 'gameMode:', gameMode)
      const result = await getOutputFormats(hands, biddingStr, dealer, gameMode, positionRoles, imageOpeningLead)
      console.log('[DEBUG] 输出格式结果:', result)
      setOutputFormats(result)
    } catch (err) {
      console.error('获取输出格式失败:', err)
    } finally {
      setOutputFormatsLoading(false)
    }
  }

  // 检验定约 - 调用Deep Finesse
  const handleAnalyzeContract = async () => {
    if (!outputFormats?.deep_finesse) return
    
    setAnalyzeLoading(true)
    setAnalyzeResult(null)
    try {
      const result = await analyzeContract(outputFormats.deep_finesse)
      setAnalyzeResult(result)
      if (!result.success) {
        alert(`检验定约失败: ${result.error}`)
      }
    } catch (err) {
      console.error('检验定约失败:', err)
      alert('检验定约失败，请检查Deep Finesse是否正确安装')
    } finally {
      setAnalyzeLoading(false)
    }
  }

  // 双明手分析
  const handleDoubleDummy = async () => {
    if (!hands) return
    
    setDoubleDummyLoading(true)
    try {
      const result = await doubleDummyAnalysis(hands)
      if (result.success) {
        setDoubleDummyResult(result.table_data)
      } else {
        alert(`双明手分析失败: ${result.error}`)
      }
    } catch (err) {
      console.error('双明手分析失败:', err)
      alert('双明手分析失败，请检查endplay是否正确安装')
    } finally {
      setDoubleDummyLoading(false)
    }
  }

  // 切换显示双明手结果
  const toggleDoubleDummy = (checked) => {
    setShowDoubleDummy(checked)
    if (checked && hands) {
      handleDoubleDummy()
    }
  }

  // ==================== 打牌相关函数 ====================

  // 统一复盘/重打初始化：playInit + 回放 keepCount 张牌
  // keepCount: 0=重新打牌, N=倒回到第N张, 'all'=全部回放
  const replayInitAndPlay = async (keepCount) => {
    const savedState = loadedPlayRecord?.playState
    if (!savedState?.contract) return { error: '无打牌记录' }

    const contract = savedState.contract

    // 构建叫牌字符串（三方共用）
    let biddingStr = null, seqStr = '', meaningLines = ''
    if (biddingSequence.length > 0) {
      seqStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      meaningLines = aiBiddingHistory
        .filter(r => r.result?.meaning)
        .map(r => `(${r.position})${r.result.bid || ''}: ${r.result.meaning}`)
        .join('\n')
      biddingStr = meaningLines
        ? `${seqStr}\n\n叫牌含义:\n${meaningLines}`
        : seqStr
    }

    // 收集所有已出牌（按顺序）
    const allPlayed = []
    for (const t of (savedState.tricks || [])) {
      for (const [pos, card] of (t.cards || [])) allPlayed.push({ pos, card })
    }
    for (const [pos, card] of (savedState.current_trick?.cards || [])) allPlayed.push({ pos, card })

    const actualKeep = keepCount === 'all' ? allPlayed.length : Math.max(0, Math.min(keepCount, allPlayed.length))

    // 计算保留的完整墩数和部分墩牌数
    let completedTricksToKeep = 0, cardsInPartialTrick = 0, accum = 0
    for (let i = 0; i < (savedState.tricks || []).length; i++) {
      const trickLen = (savedState.tricks[i].cards || []).length
      if (accum + trickLen <= actualKeep) { completedTricksToKeep++; accum += trickLen }
      else { cardsInPartialTrick = actualKeep - accum; break }
    }
    if (cardsInPartialTrick === 0 && accum < actualKeep) cardsInPartialTrick = actualKeep - accum

    // playInit
    const initResult = await playInit(
      hands,
      `${contract.level}${contract.suit}`,
      contract.declarer,
      positionRoles,
      contract.doubled || contract.isDouble || false,
      contract.redoubled || contract.isRedouble || false,
      biddingStr,
      seqStr,
      meaningLines
    )
    if (!initResult.success) return { error: initResult.error }

    // 回放前 actualKeep 张牌
    let lastReplayState = initResult.state
    for (let i = 0; i < actualKeep; i++) {
      const { pos, card } = allPlayed[i]
      try {
        const reply = await playCard(pos, card)
        if (reply?.success) lastReplayState = reply.state
      } catch (e) { console.warn('回放出牌失败:', pos, card, e) }
    }

    // 构建截断后的 playState
    const keptTricks = (savedState.tricks || []).slice(0, completedTricksToKeep)
    const partialCards = cardsInPartialTrick > 0
      ? (savedState.tricks?.[completedTricksToKeep]?.cards || []).slice(0, cardsInPartialTrick)
      : []
    const isLead = actualKeep === 0
    const allReplayed = actualKeep >= allPlayed.length

    const truncatedState = lastReplayState
      ? {
          ...lastReplayState,
          tricks: keptTricks,
          current_trick: partialCards.length > 0
            ? { cards: partialCards, leader: partialCards[0]?.[0] || null, trump: contract.suit || null }
            : { cards: [], leader: null, trump: contract.suit || null },
          phase: allReplayed ? savedState.phase : (isLead ? 'lead' : 'playing'),
        }
      : {
          ...savedState,
          tricks: keptTricks,
          current_trick: partialCards.length > 0
            ? { cards: partialCards, leader: partialCards[0]?.[0] || null, trump: contract.suit || null }
            : { cards: [], leader: null, trump: contract.suit || null },
          current_player: null,
          phase: allReplayed ? savedState.phase : (isLead ? 'lead' : 'playing'),
          declarer_tricks: keptTricks.filter(t =>
            t.winner === contract.declarer || t.winner === savedState.dummy
          ).length,
          defender_tricks: keptTricks.filter(t =>
            t.winner && t.winner !== contract.declarer && t.winner !== savedState.dummy
          ).length,
        }

    // 裁剪 aiPlayHistory
    let trimmedHistory = []
    if (loadedPlayRecord.aiPlayHistory?.length > 0) {
      const aiPositions = new Set(
        Object.entries(loadedPlayRecord.position_roles || positionRoles)
          .filter(([, role]) => role === 'ai')
          .map(([pos]) => pos)
      )
      let historyIdx = 0
      for (let i = 0; i < actualKeep; i++) {
        const pos = allPlayed[i].pos
        if (aiPositions.has(pos) && historyIdx < loadedPlayRecord.aiPlayHistory.length) {
          trimmedHistory.push(loadedPlayRecord.aiPlayHistory[historyIdx])
          historyIdx++
        }
      }
    }

    return { success: true, allPlayed, actualKeep, truncatedState, trimmedHistory, seqStr, meaningLines }
  }

  // ── 统一回放入口：导入查看 / 倒回 / 重新打牌 共用 ──
  // keepCount: 'all'=全部回放(查看), 0=全新开始(重打), N=回放到第N张(倒回)
  const startReplay = async (keepCount) => {
    const savedState = loadedPlayRecord?.playState
    if (!savedState?.contract) return

    setPlayLoading(true)
    setError(null)
    try {
      const result = await replayInitAndPlay(keepCount)
      if (result?.error) { console.error('回放失败:', result.error); return }

      const isFresh = (keepCount === 0)

      setPlayState(result.truncatedState)
      setAiPlayHistory(isFresh ? [] : result.trimmedHistory)
      setLastCompletedTrick(null)
      setShowPlayPanel(true)
      setIsPlayPaused(isFresh ? false : true)
      setPlayInitiated(true)
      setPlayStarted(isFresh ? false : result.actualKeep > 0)
      setReviewCursor(null)
      if (isFresh) {
        setLoadedPlayRecord(null)
        setCurrentRecordId(null)
        setSelectedPlayRecord(null)
        setPlayCenterView('play')
      }
    } catch (err) {
      console.error('回放失败:', err)
    } finally {
      setPlayLoading(false)
    }
  }

  // 开始打牌
  const handleStartPlay = async () => {
    if (loadedPlayRecord) {
      await startReplay('all')
      // 完成后定位到末尾，方便复盘翻牌
      const savedState = loadedPlayRecord.playState
      const totalCards = (savedState.tricks || []).reduce((s, t) => s + (t.cards?.length || 0), 0)
        + (savedState.current_trick?.cards?.length || 0)
      setReviewCursor(totalCards)
      return
    }

    const contract = getFinalContract() || directPlayContractInfo

    // 始终弹出定约确认对话框，预填识别到的信息以便调整
    if (contract) {
      const suitLetter = { '♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C', 'S': 'S', 'H': 'H', 'D': 'D', 'C': 'C', 'NT': 'NT' }[contract.suit] || contract.suit
      const contractStr = `${contract.level}${suitLetter}${contract.isDouble ? 'X' : ''}${contract.isRedouble ? 'XX' : ''}`
      setContractDialogForm({
        contractStr,
        declarer: contract.declarer,
        openingLead: imageOpeningLead || '',
        isDouble: contract.isDouble || false,
        isRedouble: contract.isRedouble || false,
      })
    } else {
      setContractDialogForm({ contractStr: '', declarer: '南', openingLead: imageOpeningLead || '', isDouble: false, isRedouble: false })
    }
    setContractDialogOpen(true)
    return
  }

  const handleRewindToTrick = async (targetCardIdx) => {
    // targetCardIdx: 从第几张牌开始重打（新游标语义 = 已出牌数量 = 下一个出牌者的牌序号）
    // 即：保留前 targetCardIdx 张牌，从第 targetCardIdx 张开始重打
    const savedState = loadedPlayRecord?.playState
    if (!savedState?.contract) return
    // 收集所有已出牌（按顺序）
    const allPlayed = []
    for (const t of (savedState.tricks || [])) {
      for (const [pos, card] of (t.cards || [])) allPlayed.push({ pos, card })
    }
    for (const [pos, card] of (savedState.current_trick?.cards || [])) allPlayed.push({ pos, card })
    // targetCardIdx = 保留的牌数量（也是开始重打的牌序号）
    const keepCount = Math.max(0, Math.min(targetCardIdx, allPlayed.length))
    // 计算保留的牌分布在哪些完整墩 + 一个可能未满的当前墩
    let completedTricksToKeep = 0
    let cardsInPartialTrick = 0
    let accum = 0
    for (let i = 0; i < (savedState.tricks || []).length; i++) {
      const trickLen = (savedState.tricks[i].cards || []).length
      if (accum + trickLen <= keepCount) {
        completedTricksToKeep++
        accum += trickLen
      } else {
        cardsInPartialTrick = keepCount - accum
        break
      }
    }
    if (cardsInPartialTrick === 0 && accum < keepCount) {
      cardsInPartialTrick = keepCount - accum
    }
    setPlayLoading(true)
    setError(null)
    try {
      const contract = savedState.contract
      let biddingStr = null
      let meaningLines = ''
      let seqStr = ''
      if (biddingSequence.length > 0) {
        seqStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
        meaningLines = aiBiddingHistory
          .filter(r => r.result?.meaning)
          .map(r => `(${r.position})${r.result.bid || ''}: ${r.result.meaning}`)
          .join('\n')
        biddingStr = meaningLines
          ? `${seqStr}\n\n叫牌含义:\n${meaningLines}`
          : seqStr
      }
      const initResult = await playInit(
        hands,
        `${contract.level}${contract.suit}`,
        contract.declarer,
        positionRoles,
        contract.doubled || contract.isDouble || false,
        contract.redoubled || contract.isRedouble || false,
        biddingStr,
        seqStr
      )
      if (!initResult.success) {
        console.error('重打初始化失败:', initResult.error)
        setPlayLoading(false)
        return
      }
      // 回放前 keepCount 张牌（完整墩 + 部分墩）
      const cardsToReplay = allPlayed.slice(0, keepCount).map(p => ({ position: p.pos, card: p.card }))
      let lastReplayState = null
      for (const { position, card } of cardsToReplay) {
        try {
          const replayResult = await playCard(position, card)
          if (replayResult?.success) lastReplayState = replayResult.state
        } catch (e) { console.warn('重放出牌失败:', position, card, e) }
      }
      // 裁剪 aiPlayHistory：按实际回放的牌筛选 AI 位置
      let trimmedHistory = []
      if (loadedPlayRecord.aiPlayHistory?.length > 0) {
        const aiPositions = new Set(
          Object.entries(loadedPlayRecord.position_roles || positionRoles)
            .filter(([, role]) => role === 'ai')
            .map(([pos]) => pos)
        )
        let historyIdx = 0
        for (let i = 0; i < keepCount; i++) {
          const pos = allPlayed[i].pos
          if (aiPositions.has(pos) && historyIdx < loadedPlayRecord.aiPlayHistory.length) {
            trimmedHistory.push(loadedPlayRecord.aiPlayHistory[historyIdx])
            historyIdx++
          }
        }
      }
      // 构建截断后的 playState（使用后端回放后的真实状态，保证 hands/current_trick 等正确）
      const keptCompletedTricks = (savedState.tricks || []).slice(0, completedTricksToKeep)
      const partialTrickCards = cardsInPartialTrick > 0
        ? (savedState.tricks?.[completedTricksToKeep]?.cards || []).slice(0, cardsInPartialTrick)
        : []
      const truncatedState = lastReplayState
        ? {
            ...lastReplayState,
            tricks: keptCompletedTricks,
            current_trick: partialTrickCards.length > 0
              ? { cards: partialTrickCards, leader: partialTrickCards[0]?.[0] || null, trump: savedState.contract?.suit || null }
              : { cards: [], leader: null, trump: savedState.contract?.suit || null },
            phase: keepCount === 0 ? 'lead' : 'playing',
          }
        : {
            ...savedState,
            tricks: keptCompletedTricks,
            current_trick: partialTrickCards.length > 0
              ? { cards: partialTrickCards, leader: partialTrickCards[0]?.[0] || null, trump: savedState.contract?.suit || null }
              : { cards: [], leader: null, trump: savedState.contract?.suit || null },
            current_player: null,
            phase: keepCount === 0 ? 'lead' : 'playing',
            declarer_tricks: keptCompletedTricks
              .filter(t => t.winner === savedState.contract?.declarer || t.winner === savedState.dummy).length,
            defender_tricks: keptCompletedTricks
              .filter(t => t.winner && t.winner !== savedState.contract?.declarer && t.winner !== savedState.dummy).length,
          }
      setPlayState(truncatedState)
      setAiPlayHistory(trimmedHistory)
      setLastCompletedTrick(null)
      setShowPlayPanel(true)
      setIsPlayPaused(true)
      setPlayInitiated(true)
      setPlayStarted(keepCount > 0)
      setReviewCursor(null)
      setCurrentRecordId(null)
    } catch (err) {
      console.error('重打失败:', err)
    } finally {
      setPlayLoading(false)
    }
  }

  // 抽取公共打牌初始化逻辑（handleStartPlay / handleResetPlay / 直接打牌 共用）
  const doPlayInit = async (contract, biddingSeq, aiHistory) => {
    setPlayLoading(true)
    setError(null)
    setIsPlayPaused(false)
    setPlayStarted(false)
    setPlayInitiated(false)
    setShowPlayedCards(true)
    prevTricksCountRef.current = 0
    setLastCompletedTrick(null)
    setReviewCursor(null)

    let biddingStr = null
    let meaningLines = ''
    let seqStr = ''
    if (biddingSeq.length > 0) {
      seqStr = biddingSeq.map(b => `(${b.position})${b.bid}`).join('-')
      meaningLines = aiHistory
        .filter(r => r.result?.meaning)
        .map(r => `(${r.position})${r.result.bid || ''}: ${r.result.meaning}`)
        .join('\n')
      biddingStr = meaningLines
        ? `${seqStr}\n\n叫牌含义:\n${meaningLines}`
        : seqStr
    }

    const playRoles = { ...positionRoles }

    try {
      const suitLetter = { '♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C', 'S': 'S', 'H': 'H', 'D': 'D', 'C': 'C', 'NT': 'NT' }[contract.suit] || contract.suit
      const contractStr = `${contract.level}${suitLetter}`
      if (!contract.level || !contract.suit) {
        setError(`定约信息不完整: ${contractStr}，请检查识别结果`)
        setLoading(false)
        return
      }
      const result = await playInit(
        hands,
        contractStr,
        contract.declarer,
        playRoles,
        contract.isDouble || false,
        contract.isRedouble || false,
        biddingStr,
        seqStr,
        meaningLines
      )

      if (result.success) {
        setPlayState(result.state)
        setShowPlayPanel(true)
        // 保留imageOpeningLead，等用户点击"开始"后再打出
      } else {
        setError(result.error || '初始化打牌失败')
      }
    } catch (err) {
      console.error('初始化打牌失败:', err)
      setError('初始化打牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayLoading(false)
    }
  }

  // 直接打牌：对话框确认，解析定约并调用 doPlayInit
  const handleContractDialogConfirm = async () => {
    const { contractStr, declarer, openingLead, isDouble, isRedouble } = contractDialogForm
    // 支持 4H、4HX、4HXX 三种格式，X/XX 由 toggle 按钮单独追踪
    const match = contractStr.trim().match(/^(\d)([SHDC]|NT)(X{1,2})?$/i)
    if (!match) {
      setError('无效定约格式，请输入如 4S、3NT、4HX 或 2SXX')
      return
    }
    const contract = {
      level: parseInt(match[1]),
      suit: match[2].toUpperCase(),
      declarer,
      isDouble: isDouble || false,
      isRedouble: isRedouble || false,
      partnership: ['南', '北'].includes(declarer) ? '南北' : '东西',
      bid: contractStr.trim(),
    }
    setDirectPlayContractInfo(contract)
    // 保存用户确认的首攻信息，供 handleBeginPlay 使用
    setImageOpeningLead(openingLead || null)
    setContractDialogOpen(false)
    // 传递截屏/识别得到的叫牌序列，确保后端能据此提取约束（避免DD显示"无约束随机采样"）
    await doPlayInit(contract, biddingSequence, aiBiddingHistory)
  }

  // 出牌
  const handlePlayCard = async (position, card) => {
    setPlayLoading(true)
    setError(null)
    
    try {
      const result = await playCard(position, card)
      
      if (result.success) {
        console.log('[DEBUG handlePlayCard] result.state.current_trick:', result.state.current_trick)
        setPlayState(result.state)
        setPlayStarted(true)
        // 人类出牌后取消暂停，让下家（AI或人类）自动衔接
        setIsPlayPaused(false)

        if (result.is_complete && result.result) {
          console.log('打牌结束:', result.result)
        }
      } else {
        setError(result.error || result.message || '出牌失败')
      }
    } catch (err) {
      console.error('出牌失败:', err)
      setError('出牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayLoading(false)
    }
  }

  // 点击牌桌上的手牌直接出牌
  const handleHandCardClick = (suitSymbol, rank) => {
    if (!playState?.current_player) return
    handlePlayCard(playState.current_player, { suit: suitSymbol, rank })
  }

  // 人类手动输入牌张（无手牌数据时）
  const handleManualPlay = (position, cardStr) => {
    cardStr = cardStr.trim()
    // 解析格式: "♠A" / "S A" / "♠10" / "SA"
    let suit, rank
    const m2 = cardStr.match(/^(\S)([2-9TJQKA]|10)$/i)
    if (m2) {
      suit = m2[1]
      rank = m2[2].toUpperCase() === '10' ? 'T' : m2[2].toUpperCase()
    } else {
      const parts = cardStr.split(/\s+/)
      if (parts.length === 2) {
        suit = parts[0]
        rank = parts[1].toUpperCase() === '10' ? 'T' : parts[1].toUpperCase()
      }
    }
    if (!suit || !rank) {
      setError('无法解析牌张，请输入如 ♠A 或 S A')
      return
    }
    // 花色标准化
    const suitMap = { 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' }
    suit = suitMap[suit.toUpperCase()] || suit
    handlePlayCard(position, { suit, rank })
  }

  const handleSetPlayHand = async (position, hand) => {
    setPlayLoading(true)
    try {
      const result = await setPlayHand(position, hand)
      if (result.success && result.state) {
        setPlayState(result.state)
        // 同步更新前端 hands 状态，避免 showInput 拦截手牌显示
        setHands(prev => ({ ...prev, [position]: hand }))
      } else {
        setError(result.error || '设置手牌失败')
      }
    } catch (err) {
      setError('设置手牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayLoading(false)
    }
  }

  // AI出牌
  const handleAIPlay = async () => {
    // 如果已有进行中的请求，先中止
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setAiThinking(true)
    setError(null)
    
    try {
      const pm = parseModelValue(playModel)
      const result = await aiPlay(pm.model, pm.reasoning, playEngine, ddSampleCount, controller.signal)
      if (controller.signal.aborted) return
      console.log('[AI Play] engine:', result.used_engine, 'elapsed:', result.elapsed_ms + 'ms', 'model:', result.used_model)

      if (result.success) {
        const aiRecord = {
          position: playState?.current_player,
          card: result.card,
          reasoning: result.reasoning,
          follow_up: result.follow_up,
          full_output: result.full_output,
          prompt: result.prompt,
          used_model: result.used_model,
          used_engine: result.used_engine,
          elapsed_ms: result.elapsed_ms,
          timestamp: makeBidTimestamp(),
        }
        setAiPlayHistory(prev => [...prev, aiRecord])
        setPlayStarted(true)
        
        const stateResult = await getPlayState()
        if (stateResult.success) {
          setPlayState(stateResult.state)
        }
      } else {
        setError(result.error || 'AI出牌失败')
      }
    } catch (err) {
      if (err.name === 'CanceledError' || err.name === 'AbortError' || controller.signal.aborted) {
        console.log('[AI Play] 用户已暂停，忽略')
        return
      }
      console.error('AI出牌失败:', err)
      setError('AI出牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
      setAiThinking(false)
    }
  }

  const handleResumePlay = () => {
    setIsPlayPaused(false)
    setLastCompletedTrick(null)
    setShowDoubleDummy(false)
    setSelectedPlayRecord(null)
    setReviewCursor(null)
  }

  // 将 "S5"/"HK" 等卡片字符串转换为 API 所需的 {suit, rank} 格式
  const parseCardStr = (cardStr) => {
    if (!cardStr) return null
    const suitMap = { S: '♠', H: '♥', D: '♦', C: '♣', '♠': '♠', '♥': '♥', '♦': '♦', '♣': '♣' }
    const match = cardStr.trim().match(/^([SHDC♠♥♦♣])([2-9TJQKA]|10)$/i)
    if (!match) return null
    return { suit: suitMap[match[1].toUpperCase()] || match[1], rank: match[2] }
  }

  // 开始打牌（从初始未开始状态进入打牌）
  const handleBeginPlay = async () => {
    // 如果有首攻信息（图片识别或用户输入），先打出首攻再启动AI
    if (imageOpeningLead) {
      // 支持英文冒号 ":" 和中文冒号 "：" 两种分隔符
      const parts = imageOpeningLead.split(/[:：]/)
      let leadPos, cardObj

      if (parts.length >= 2) {
        // 完整格式: "西:S5" 或 "西:DA"
        leadPos = parts[0].trim()
        cardObj = parseCardStr(parts.slice(1).join(':'))
      } else {
        // 只有牌张没有位置: "S5"、"DA"、"♠5" → 用当前应出牌人的位置
        cardObj = parseCardStr(imageOpeningLead.trim())
        if (cardObj) {
          // 首攻人就是当前回合的玩家（playState初始化后current_player=lead_player）
          leadPos = playState?.current_player
        }
      }

      if (leadPos && cardObj) {
        try {
          const playResult = await playCard(leadPos, cardObj)
          if (playResult.success) {
            setPlayState(playResult.state)
            setPlayStarted(true)
          } else {
            setError(playResult.error || '首攻出牌失败')
            return
          }
        } catch (e) {
          console.warn('首攻出牌失败:', e)
          setError('首攻出牌失败: ' + (e.response?.data?.detail || e.message))
          return
        }
        // 首攻打出后再启动AI自动出牌
        setPlayInitiated(true)
        setIsPlayPaused(false)
        return
      } else {
        // 解析失败，提示但不清除输入
        if (!cardObj) {
          setError(`首攻牌张无效: "${imageOpeningLead}"，请输入花色+牌面（如 S5、DA、♠K）或完整格式 西:S5`)
        } else {
          setError(`无法确定首攻人位置，请加上位置，如 西:${imageOpeningLead}`)
        }
        return
      }
    }
    // 没有首攻信息，正常开始
    setPlayInitiated(true)
    setIsPlayPaused(false)
  }

  // 暂停打牌（立即中止AI请求）
  const handlePausePlay = () => {
    setIsPlayPaused(true)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }

  // 撤销最近一次出牌
  const handleUndoPlay = async () => {
    try {
      // 记录撤销前的状态，用于判断撤销了谁出的牌
      
      const result = await undoPlay()
      if (result.success) {
        const state = result.state
        setPlayState(state)
          setSelectedPlayRecord(null)
        
        // 撤销的牌是刚出的那张，出牌者现在是current_player（撤销后轮到他重新出牌）
        // 如果这张牌是AI出的，从aiPlayHistory中删除对应记录
        const undonePlayer = state.current_player
        // 检查aiPlayHistory最后一条是否属于被撤销的出牌者
        setAiPlayHistory(prev => {
          if (prev.length > 0) {
            const lastRecord = prev[prev.length - 1]
            // 如果最后一条AI记录的位置和被撤销的出牌者匹配，删除它
            if (lastRecord.position === undonePlayer) {
              return prev.slice(0, -1)
            }
          }
          return prev
        })
        
        // 同步更新墩数计数器，避免"一墩完成自动暂停"误触发
        const newTricksCount = state.tricks?.length || 0
        prevTricksCountRef.current = newTricksCount
        
        // 更新lastCompletedTrick以匹配撤销后的状态
        if (newTricksCount > 0) {
          setLastCompletedTrick(state.tricks[newTricksCount - 1])
        } else {
          setLastCompletedTrick(null)
        }
        
        // 判断撤销后是否还有已出牌
        const hasPlayedCards = newTricksCount > 0 || 
                               (state.current_trick?.cards && state.current_trick.cards.length > 0)
        if (!hasPlayedCards) {
          // 撤销到没有已出牌时，重置为未开始状态
          setPlayStarted(false)
          setPlayInitiated(false)
        } else {
          setPlayStarted(true)
        }
        
        // 撤销后暂停，让用户决定下一步
        setIsPlayPaused(true)
      } else {
        setError(result.error || result.message || '撤销失败')
      }
    } catch (err) {
      console.error('撤销出牌失败:', err)
      setError('撤销出牌失败')
    }
  }

  // 返回叫牌界面（放弃打牌过程和数据）
  const handleBackToBidding = () => {
    if (!window.confirm('确定要返回叫牌界面吗？\n\n当前的打牌过程和数据将被丢弃，但叫牌序列和手牌会保留。')) {
      return
    }
    setPlayState(null)
    setAiPlayHistory([])
    setShowPlayPanel(false)
    setIsPlayPaused(false)
    setPlayInitiated(false)
    setPlayStarted(false)
    setLoadedPlayRecord(null)
    setSelectedPlayRecord(null)
    setReviewCursor(null)
    setLastCompletedTrick(null)
    console.log('[Play] 已返回叫牌界面，打牌数据已清除')
  }

  // 重新打牌（保持当前牌局和叫牌，重置打牌状态并重新初始化）
  const handleResetPlay = async () => {
    let contract = getFinalContract()
    if (!contract) contract = directPlayContractInfo
    if (!contract) {
      setError('无法确定定约')
      return
    }

    setResetOpeningLeadValue(imageOpeningLead || '')
    setResetOpeningLeadDialogOpen(true)
  }

  const doResetPlay = async (contract) => {
    if (loadedPlayRecord) {
      await startReplay(0)
    } else {
      await doPlayInit(contract, biddingSequence, aiBiddingHistory)
    }
  }

  const handleResetOpeningLeadConfirm = (action) => {
    setResetOpeningLeadDialogOpen(false)
    let contract = getFinalContract()
    if (!contract) contract = directPlayContractInfo

    if (action === 'keep') {
      // 保留当前首攻
    } else if (action === 'clear') {
      setImageOpeningLead(null)
    } else if (action === 'edit') {
      setImageOpeningLead(resetOpeningLeadValue || null)
    }
    doResetPlay(contract)
  }

  // 桌面点击已出牌，切换到对应的打牌细节
  const handlePlayCardClick = (position, card) => {
    if (!aiPlayHistory || aiPlayHistory.length === 0) return
    const found = aiPlayHistory.find(record =>
      record.position === position &&
      record.card?.suit === card.suit &&
      record.card?.rank === card.rank
    )
    if (found) {
      setSelectedPlayRecord(found)
    }
  }

  // 根据前端 positionRoles 计算当前回合是否为人类
  const isCurrentPlayerHuman = () => {
    if (!playState) return false
    const cp = playState.current_player
    if (!cp) return false
    if (cp === playState.dummy) {
      return positionRoles[playState.contract?.declarer] === 'human'
    }
    return positionRoles[cp] === 'human'
  }

  // 牌桌DD提示获取
  useEffect(() => {
    if (!showPlayPanel || !playState) return
    if (!showDDHints) { setDDHints(null); return }

    // 只要四家手牌都已知就计算 DD（导入时已从 tricks 重建）
    const ALL_POS = ['南', '北', '东', '西']
    const suitMap = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }
    const fullHands = {}
    let allKnown = true
    for (const p of ALL_POS) {
      const h = hands?.[p]
      if (h && ((h.spades || '') + (h.hearts || '') + (h.diamonds || '') + (h.clubs || '')).length > 0) {
        fullHands[p] = []
        for (const sk of ['spades', 'hearts', 'diamonds', 'clubs']) {
          for (const r of (h[sk] || '')) {
            if ('AKQJT98765432'.includes(r.toUpperCase())) fullHands[p].push({ suit: suitMap[sk], rank: r.toUpperCase() })
          }
        }
      } else {
        allKnown = false
      }
    }
    if (!allKnown) { setDDHints(null); return }

    // 复盘：通过游标重建牌局快照
    if (reviewCursor != null) {
      const totalCards = (playState.tricks || []).reduce((s, t) => s + (t.cards?.length || 0), 0)
        + (playState.current_trick?.cards?.length || 0)
      if (reviewCursor >= totalCards) { setDDHints(null); return }
      setDDHints(null)
      setDDHintsLoading(true)
      let cancelled = false
      getDDHintsReview({ ...playState, hands: fullHands }, reviewCursor)
        .then(data => { if (!cancelled && data?.success) setDDHints(data.hints) })
        .catch(err => { if (!cancelled) console.error('DD hints review fetch failed:', err) })
        .finally(() => { if (!cancelled) setDDHintsLoading(false) })
      return () => { cancelled = true }
    }

    // 实战：直接用后端当前状态
    if (playState.phase === 'complete') return
    setDDHints(null)
    setDDHintsLoading(true)
    let cancelled = false
    getDDHints()
      .then(data => { if (!cancelled && data?.success) setDDHints(data.hints) })
      .catch(err => { if (!cancelled) console.error('DD hints fetch failed:', err) })
      .finally(() => { if (!cancelled) setDDHintsLoading(false) })
    return () => { cancelled = true }
  }, [showDDHints, playState?.current_player, playState?.phase, showPlayPanel, reviewCursor, playState, hands])

  // 加载记录后自动进入打牌界面（记录含打牌数据时）
  useEffect(() => {
    if (loadedPlayRecord && !showPlayPanel) {
      handleStartPlay()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedPlayRecord])

  // AI自动出牌
  useEffect(() => {
    if (!showPlayPanel || !playState || aiThinking || playLoading || isPlayPaused || !playInitiated) return

    const { phase } = playState
    const isHuman = isCurrentPlayerHuman()


    // AI hand guard: wait for input when AI has no cards
    if (!isHuman) {
      const currentHand = playState.hands?.[playState.current_player]
      if (!currentHand || currentHand.length === 0) return
    }
    // 如果不是人类回合且游戏未结束，自动AI出牌
    if (!isHuman && phase !== 'complete') {
      const timer = setTimeout(() => {
        handleAIPlay()
      }, 500) // 延迟500ms让用户看到状态变化

      return () => clearTimeout(timer)
    }
  }, [playState?.is_human_turn, playState?.phase, showPlayPanel, aiThinking, playLoading, isPlayPaused, playInitiated, positionRoles])

  // 最后一墩自动出牌（仅剩一张时无需选择）
  useEffect(() => {
    if (!showPlayPanel || !playState || aiThinking || playLoading || isPlayPaused || !playInitiated) return
    if (playState.phase === 'complete') return
    const cp = playState.current_player
    if (!cp) return
    const isHuman = positionRoles[cp] === 'human' || (cp === playState.dummy && positionRoles[playState.contract?.declarer] === 'human')
    if (!isHuman) return
    const handLen = playState.hands?.[cp]?.length || 0
    if (handLen === 1) {
      const card = playState.hands[cp][0]
      const timer = setTimeout(() => handlePlayCard(cp, card), 400)
      return () => clearTimeout(timer)
    }
  }, [playState?.current_player, playState?.hands?.[playState?.current_player]?.length, showPlayPanel, playInitiated, aiThinking, playLoading, isPlayPaused])

  // 轮到人类出牌时自动暂停（每墩首张除外，由继续按钮控制）
  useEffect(() => {
    if (!showPlayPanel || !playState || aiThinking || playLoading || !playInitiated) return
    const isHuman = isCurrentPlayerHuman()
    const isStartOfTrick = (playState.current_trick?.cards?.length || 0) === 0
    if (isHuman && playState.phase !== 'complete' && !isPlayPaused && !isStartOfTrick) {
      setIsPlayPaused(true)
    }
  }, [playState?.is_human_turn, playState?.phase, showPlayPanel, playInitiated, aiThinking, playLoading, isPlayPaused, positionRoles])

  // 检测一墩完成，自动暂停；检测打牌完成，自动保存记录
  useEffect(() => {
    if (!showPlayPanel || !playState) return

    const currentTricksCount = playState.tricks?.length || 0
    const prevTricksCount = prevTricksCountRef.current
    const phase = playState.phase

    // 一墩完成时不自动暂停（连续自动打牌，手动暂停按钮仍可用）
    if (currentTricksCount > prevTricksCount && playState.tricks && playState.tricks.length > 0) {
      const lastTrick = playState.tricks[playState.tricks.length - 1]
      setLastCompletedTrick(lastTrick)
      setSelectedPlayRecord(null)
    }

    // 打牌完成，自动保存完整记录 + 自动进入复盘模式
    if (phase === 'complete' && prevTricksCount < 13) {
      console.log('[自动保存] 打牌完成 phase=complete, 准备保存完整记录');
      saveCompletePlayRecord()
      // 新完成的打牌停在全部已出位置
      const totalCards = (playState.tricks || []).reduce((s, t) => s + (t.cards?.length || 0), 0)
        + (playState.current_trick?.cards?.length || 0)
      setReviewCursor(totalCards)
    }

    prevTricksCountRef.current = currentTricksCount
  }, [playState?.tricks?.length, playState?.phase, showPlayPanel])

  // 保存打牌完成的完整记录
  const saveCompletePlayRecord = useCallback(() => {
    if (!playState || playState.phase !== 'complete') return

    // 从第一墩第一张牌提取首攻
    let openingLead = imageOpeningLead || undefined
    if (!openingLead && playState.tricks?.length > 0) {
      const firstTrick = playState.tricks[0]
      if (firstTrick.cards?.length > 0) {
        const [leadPos, leadCard] = firstTrick.cards[0]
        openingLead = `${leadPos}:${leadCard.suit}${leadCard.rank}`
      }
    }

    const finalContract = getFinalContract() || directPlayContractInfo
    const record = {
      id: Date.now().toString(),
      timestamp: new Date().toLocaleString(),
      type: 'play_complete',
      sourceRecordId: currentRecordId || undefined,
      board: {
        hands: hands,
        bidding_sequence: biddingSequence,
        contract: finalContract,
        dealer: dealer,
        game_mode: gameMode,
        practice_direction: practiceDirection,
        position_roles: positionRoles,
        opening_lead: openingLead,
      },
      bidding: {
        ai_bidding_history: trimBiddingHistory(aiBiddingHistory),
        deal_system: dealSystem,
      },
      play: {
        tricks: playState.tricks,
        ai_play_history: trimPlayHistory(aiPlayHistory),
        declarer_tricks: playState.declarer_tricks,
        defender_tricks: playState.defender_tricks,
      },
      note: ''
    }
    saveBridgeRecord(record)
    console.log('[自动保存] 打牌记录已调用保存, id:', record.id)
    // 如果之前没有记录ID，保存后设置当前记录ID
    if (!currentRecordId) {
      setCurrentRecordId(record.id)
    }
  }, [playState, hands, biddingSequence, dealer, gameMode, practiceDirection, positionRoles, directPlayContractInfo, aiBiddingHistory, dealSystem, aiPlayHistory, currentRecordId, imageOpeningLead])

  // 处理位置角色变化：所有位置全手动设置，无连锁
  const handlePositionRoleChange = async (position, role) => {
    const newRoles = { ...positionRoles, [position]: role }
    setPositionRoles(newRoles)

    // 每墩开头：当前玩家从人类切为AI时自动暂停，显示继续按钮
    if (showPlayPanel && playState && !isPlayPaused && playState.phase !== 'complete') {
      const isStartOfTrick = (playState.current_trick?.cards?.length || 0) === 0
      if (isStartOfTrick && newRoles[playState.current_player] === 'ai') {
        setIsPlayPaused(true)
      }
    }

    // 如果在打牌阶段，同步更新后端的 player_roles
    if (showPlayPanel && playState) {
      try {
        const result = await updatePlayPlayerRoles(newRoles)
        if (result.success) {
          setPlayState(result.state)
        }
      } catch (err) {
        console.error('更新打牌角色失败:', err)
      }
    }
  }


  return (
    <Box sx={{ maxWidth: 1400, mx: 'auto', py: { xs: 1.5, md: 2.5 }, px: { xs: 1, md: 3 } }}>
      {/* 草稿恢复提示横幅 */}
      {showDraftBanner && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button color="inherit" size="small" onClick={clearBiddingDraft}>
                忽略
              </Button>
              <Button color="primary" size="small" variant="outlined" onClick={restoreBiddingDraft}>
                恢复
              </Button>
            </Box>
          }
        >
          检测到上次未完成的叫牌，是否需要恢复？
        </Alert>
      )}
      <Header
        onModeChange={handleModeChange}
        mode={mode}
        showSettings={showSettings}
        setShowSettings={setShowSettings}
        loading={loading}
        handleDeal={handleDeal}
        dealMode={dealMode}
        biddingRecords={bridgeRecords}
        setHistoryDialogOpen={setHistoryDialogOpen}
        checkApiStatus={checkApiStatus}
        apiStatus={apiStatus}
        handleReloadJF={handleReloadJF}
        darkMode={darkMode}
        onToggleDarkMode={onToggleDarkMode}
        aiThinking={aiThinking}
        vulnerability={vulnerability}
        setVulnerability={setVulnerability}
      />
      {/* 游戏设置 */}
      <SettingsPanel
        showSettings={showSettings}
        gameMode={gameMode}
        setGameMode={setGameMode}
        fallbackModel={fallbackModel}
        handleFallbackModelChange={handleFallbackModelChange}
        playModel={playModel}
        handlePlayModelChange={handlePlayModelChange}
        playEngine={playEngine}
        handlePlayEngineChange={handlePlayEngineChange}
        ddSampleCount={ddSampleCount}
        handleDDSampleCountChange={handleDDSampleCountChange}
        ddParticles={ddParticles} ddParticlesRange={ddParticlesRange}
        mctsParticles={mctsParticles} mctsParticlesRange={mctsParticlesRange}
        alphaMuParticles={alphaMuParticles} alphaMuParticlesRange={alphaMuParticlesRange}
        handleParticleChange={handleParticleChange}
        dealSystem={dealSystem}
        setDealSystem={setDealSystem}
        dealMode={dealMode}
        setDealMode={setDealMode}
        vulnerability={vulnerability}
        setVulnerability={setVulnerability}
        loading={loading}
        mode={mode}
        hands={hands}
        availableModels={availableModels}
      />

      {/* 错误提示 */}
      {error && (
        <Alert severity="error" onClose={() => { screenshotCancelledRef.current = true; setError(null) }} sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}
      {warning && (
        <Alert
          severity="warning"
          onClose={() => setWarning(null)}
          sx={{ mb: 3 }}
        >
          {warning}
        </Alert>
      )}

      {/* 牌桌主区域（桌面横排 / 手机纵排，由 MainTableArea 内部处理） */}
      {hands && (
        <MainTableArea
          isMobile={isMobile}
          declarer={finalContract?.declarer || directPlayContractInfo?.declarer}
          finalContract={finalContract}
          directPlayContractInfo={directPlayContractInfo}
          onAnalyzeContract={handleAnalyzeContract}
          onToggleDoubleDummy={toggleDoubleDummy}
          onDealerChange={handleDealerChange}
          onPositionRoleChange={handlePositionRoleChange}
          onClearAllHands={clearAllHands}
          onEditHands={() => {
            setCustomDealText(handsToEditText(hands))
            setCustomDealOpen(true)
          }}
          onEditBidding={() => {
            setEditBiddingText(biddingToEditText(biddingSequence))
            setShowEditBiddingDialog(true)
          }}
          onPlayCardClick={handlePlayCardClick}
          onSetPlayHand={handleSetPlayHand}
          onImageDeal={() => setImageDealOpen(true)}
          onScreenshotDeal={onScreenshotDeal}
          onSingleHandScreenshot={handleSingleHandScreenshot}
          onCustomDeal={() => setCustomDealOpen(true)}
          onDeal={handleDeal}
          onHandCardClick={handleHandCardClick}
          onManualPlay={handleManualPlay}
          addBid={addBid}
          startBidding={startBidding}
          // 叫牌面板回调
          onStartPlay={handleStartPlay}
          onResetBidding={resetBidding}
          onToggleStopBidding={toggleStopBidding}
          onUndoBidding={undoBidding}
          onSaveBidding={handleSaveProgress}
          canSaveBiddingProgress={canSaveProgress}
          showUndoBidding={showUndo}
          canUndoBidding={canUndo}
          onStartBidding={startBidding}
          // 打牌面板回调
          onResume={handleResumePlay}
          onResetPlay={handleResetPlay}
          onClearExternalRecord={() => setSelectedPlayRecord(null)}
          onBeginPlay={handleBeginPlay}
          onPausePlay={handlePausePlay}
          onUndoPlay={handleUndoPlay}
          onSavePlay={handleSaveProgress}
          canSavePlay={playCanSave}
          onBackToBidding={handleBackToBidding}
          onReviewPrev={() => setReviewCursor(c => Math.max(0, (c || 0) - 1))}
          onReviewNext={() => setReviewCursor(c => {
            const totalCards = (playState?.tricks || []).reduce((s, t) => s + (t.cards?.length || 0), 0)
              + (playState?.current_trick?.cards?.length || 0)
            return Math.min(totalCards, (c || 0) + 1)
          })}
          onRewindToTrick={handleRewindToTrick}
        />
      )}

      {/* 使用说明 */}
      {!hands && (
        <Paper elevation={1} sx={{ p: 3, mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            使用说明
          </Typography>
          <Typography variant="body1" component="div">
            <strong>开始练习：</strong><br />
            1. 点击"设置"选择叫牌模式（四人/双人）、发牌人位置和人类玩家位置<br />
            2. 点击"发牌"生成新牌局，或使用自定义牌局/图片识别功能<br />
            3. 人类回合时右侧面板显示叫牌按钮，AI回合自动叫牌<br />
            <br />
            <strong>界面说明：</strong><br />
            • 当前牌局：可切换显示小房子/叫牌结果，勾选显示AI手牌或队友手牌<br />
            • 叫牌细节：人类叫牌时显示JF约定片段作为参考
          </Typography>
        </Paper>
      )}

      {/* 历史记录对话框 */}
      <HistoryDialog
        open={historyDialogOpen}
        onClose={() => setHistoryDialogOpen(false)}
        records={bridgeRecords}
        onLoad={loadRecordToTable}
        onDelete={(ids) => deleteBridgeRecords(ids)}
        onExport={(records) => {
          try {
            if (records.length === 0) { setError('没有可导出的记录'); return }
            const exportData = { version: '2.0', exportDate: new Date().toISOString(), records }
            const dataStr = JSON.stringify(exportData, null, 2)
            const blob = new Blob([dataStr], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = `bridge_records_${new Date().toISOString().slice(0, 10)}.json`
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(url)
          } catch (err) {
            console.error('导出记录失败:', err)
            setError('导出记录失败')
          }
        }}
        onImport={importRecords}
        onUpdateNote={updateRecordNote}
        onError={setError}
      />

      {/* 自定义牌局对话框 */}
      <Dialog open={customDealOpen} onClose={() => { setCustomDealOpen(false); setHandsValidationError([]); setHandsValidationWarning([]) }} maxWidth="md" fullWidth>
        <DialogTitle>修正手牌</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            支持多种格式（按南西北东顺序，每行一家）：<br />
            格式1 - 标准格式：<br />
            K85 AT863 Q42 63<br />
            格式2 - 带花色符号（修正手牌时使用）：<br />
            ♠KT85 ♥AT863 ♦Q42 ♣63<br />
            格式3 - Deep Finesse格式<br />
            <br />
            用 - 或空字符串表示缺门。行内用空格分隔四个花色。<br />
            允许只修改部分玩家：未编辑的位置（0张）保留原手牌数据。
          </Alert>
          <TextField
            multiline
            rows={8}
            fullWidth
            value={customDealText}
            onChange={(e) => { setCustomDealText(e.target.value); setHandsValidationError([]); setHandsValidationWarning([]) }}
            placeholder="请输入牌局..."
          />
          {handsValidationError.length > 0 && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {handsValidationError.map((err, i) => (<div key={i}>• {err}</div>))}
            </Alert>
          )}
          {handsValidationWarning.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {handsValidationWarning.map((w, i) => (<div key={i}>• {w}</div>))}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setCustomDealOpen(false); setHandsValidationError([]); setHandsValidationWarning([]) }}>取消</Button>
          <Button onClick={async () => {
            if (!customDealText.trim()) return
            // 解析原始文本，记录每行是否为空（用于区分"未编辑"和"主动清空"）
            const rawLines = customDealText.split('\n')
            const posOrder = ['南', '西', '北', '东']
            const lineIsEmpty = posOrder.map((_, i) => !(rawLines[i] || '').trim())

            // 直接调用解析API，不使用 handleCustomDeal（避免 resetGameState 清空打牌/叫牌状态）
            setLoading(true)
            let parsedHands
            try {
              const resp = await apiCustomDeal(customDealText)
              if (!resp.success) {
                setHandsValidationError([resp.message || '牌局解析失败'])
                return
              }
              parsedHands = resp.hands
            } catch {
              setHandsValidationError(['牌局解析失败，请检查API服务'])
              return
            } finally {
              setLoading(false)
            }

            // 校验手牌：每家13张或0张、无重复、四家52张（仅当四家都有牌时）
            const validation = validateHands(parsedHands)
            if (!validation.valid) {
              setHandsValidationError(validation.errors)
              setHandsValidationWarning(validation.warnings)
              return
            }
            // 合并：空行保留原数据（未编辑），非空行使用新数据（包括0张主动清空）
            const mergedHands = { ...parsedHands }
            for (let i = 0; i < 4; i++) {
              if (lineIsEmpty[i] && hands?.[posOrder[i]]) {
                mergedHands[posOrder[i]] = { ...hands[posOrder[i]] }
              }
            }
            setHands(mergedHands)
            // 打牌阶段：同步后端 playState（"修正后的完整牌 - 已打出牌 = 剩余牌"再同步，
            // 确保修正后的明手牌能正确驱动 AI 出牌，且不会把已打出的牌加回）
            if (showPlayPanel && playState) {
              const suitToKey = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
              const played = {} // pos -> Set("suit rank")
              const collectPlayed = (trick) => {
                ;(trick?.cards || []).forEach(([pos, card]) => {
                  if (!played[pos]) played[pos] = new Set()
                  played[pos].add(`${card.suit}${card.rank}`)
                })
              }
              ;(playState.tricks || []).forEach(collectPlayed)
              collectPlayed(playState.current_trick)
              for (const pos of ['南', '西', '北', '东']) {
                const h = mergedHands[pos]
                if (!h) continue
                const cards = []
                for (const key of ['spades', 'hearts', 'diamonds', 'clubs']) {
                  for (const r of (h[key] || '')) {
                    cards.push({ suit: { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[key], rank: r.toUpperCase() })
                  }
                }
                const remainingCards = cards.filter(c => !played[pos]?.has(`${c.suit}${c.rank}`))
                if (remainingCards.length === 0) continue
                const remainingHand = { spades: '', hearts: '', diamonds: '', clubs: '' }
                remainingCards.forEach(c => { remainingHand[suitToKey[c.suit]] += c.rank })
                try {
                  const playResult = await setPlayHand(pos, remainingHand)
                  if (playResult?.success && playResult.state) setPlayState(playResult.state)
                } catch {
                  // 非打牌阶段调用失败，忽略
                }
              }
            }
            setHandsValidationError([])
            setHandsValidationWarning([])
            setCustomDealOpen(false)
            setCustomDealText('')
            // 修正后立即保存牌局，确保历史记录中是完整手牌
            saveBridgeRecord({
              id: currentRecordId || Date.now().toString(),
              timestamp: new Date().toLocaleString(),
              type: 'bidding_in_progress',
              board: {
                hands: mergedHands,
                bidding_sequence: [],
                contract: null,
                dealer: dealer,
                game_mode: gameMode,
                practice_direction: practiceDirection,
                position_roles: positionRoles,
              },
              bidding: { ai_bidding_history: [], deal_system: dealSystem },
              play: null,
              note: '',
            })
            if (currentRecordId) loadBridgeRecords()
          }} variant="contained" disabled={!customDealText.trim() || loading}>
            {loading ? <CircularProgress size={20} /> : '确定'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 编辑叫牌对话框 */}
      <Dialog open={showEditBiddingDialog} onClose={() => { setShowEditBiddingDialog(false); setBiddingValidationError([]); setBiddingValidationWarning([]) }} maxWidth="md" fullWidth>
        <DialogTitle>编辑叫牌序列</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            格式：(位置)叫品，用 - 分隔。例如：(北)pass-(东)1H-(南)pass-(西)2D-...
          </Alert>
          <TextField
            multiline
            rows={4}
            fullWidth
            value={editBiddingText}
            onChange={(e) => { setEditBiddingText(e.target.value); setBiddingValidationError([]); setBiddingValidationWarning([]) }}
            placeholder="输入叫牌序列..."
          />
          {biddingValidationError.length > 0 && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {biddingValidationError.map((err, i) => (<div key={i}>• {err}</div>))}
            </Alert>
          )}
          {biddingValidationWarning.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {biddingValidationWarning.map((w, i) => (<div key={i}>• {w}</div>))}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setShowEditBiddingDialog(false); setBiddingValidationError([]); setBiddingValidationWarning([]) }}>取消</Button>
          <Button onClick={() => {
            if (editBiddingText.trim()) {
              const parsed = parseBiddingSequenceStr(editBiddingText)
              if (parsed.length === 0) {
                setBiddingValidationError(['叫牌格式解析失败，请检查格式'])
                return
              }
              // 校验叫牌：位置连续性、叫品合法性、阶数递增、X/XX合法性
              const validation = validateBidding(parsed, dealer)
              if (!validation.valid) {
                setBiddingValidationError(validation.errors)
                setBiddingValidationWarning(validation.warnings)
                return
              }
              setBiddingValidationError([])
              setBiddingValidationWarning(validation.warnings)
              // 使用标准化后的序列（处理pass=、X、XX等）
              setBiddingSequence(validation.normalized)
              setShowEditBiddingDialog(false)
            }
          }} variant="contained">
            确定
          </Button>
        </DialogActions>
      </Dialog>

      {/* 图片牌局对话框 */}
      <Dialog open={imageDealOpen} onClose={() => setImageDealOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>从图片读取牌局</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            支持 jpg/png/gif/webp 格式的图片
          </Alert>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <TextField
              fullWidth
              value={imagePath}
              placeholder="请选择图片文件..."
              InputProps={{ readOnly: true }}
            />
            <Button
              variant="outlined"
              component="label"
              sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
            >
              浏览...
              <input
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) {
                    setImagePath(file.name)
                    setImageFile(file)
                  }
                }}
              />
            </Button>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setImageDealOpen(false)
            setImagePath('')
            setImageFile(null)
          }}>取消</Button>
          <Button onClick={async () => {
            if (imageFile) {
              await handleImageDeal(imageFile)
              setImageDealOpen(false)
              setImagePath('')
              setImageFile(null)
            }
          }} variant="contained" disabled={!imageFile || loading}>
            {loading ? <CircularProgress size={20} /> : '确定'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 进入打牌前确认/调整定约与首攻 */}
      <Dialog open={contractDialogOpen} onClose={() => setContractDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>确认定约与首攻</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <Alert severity={contractDialogForm.contractStr ? 'success' : 'info'}>
              {contractDialogForm.contractStr
                ? '已识别到定约信息，确认或调整后开始打牌'
                : '未检测到定约，请手动输入后进入打牌'}
            </Alert>
            <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
              <TextField
                label="定约"
                placeholder="例如 4S 或 3NT"
                value={contractDialogForm.contractStr}
                onChange={(e) => setContractDialogForm({ ...contractDialogForm, contractStr: e.target.value.replace(/\s/g, '').toUpperCase() })}
                size="small"
                sx={{ flex: '0 0 140px' }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleContractDialogConfirm() }}
              />
              <FormControl size="small" sx={{ flex: '0 0 100px' }}>
                <InputLabel>庄家</InputLabel>
                <Select
                  value={contractDialogForm.declarer}
                  label="庄家"
                  onChange={(e) => setContractDialogForm({ ...contractDialogForm, declarer: e.target.value })}
                >
                  {['南', '北', '东', '西'].map(pos => (
                    <MenuItem key={pos} value={pos}>{pos}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <ToggleButtonGroup
                size="small"
                value={
                  contractDialogForm.isRedouble ? 'XX' :
                  contractDialogForm.isDouble ? 'X' : ''
                }
                exclusive
                onChange={(_, val) => {
                  if (val === null) return
                  setContractDialogForm({
                    ...contractDialogForm,
                    isDouble: val === 'X' || val === 'XX',
                    isRedouble: val === 'XX',
                  })
                }}
              >
                <ToggleButton value="" sx={{ fontSize: '0.75rem', px: 1 }}>—</ToggleButton>
                <ToggleButton value="X" sx={{ fontSize: '0.75rem', px: 1, fontWeight: 700 }}>X</ToggleButton>
                <ToggleButton value="XX" sx={{ fontSize: '0.75rem', px: 1, fontWeight: 700 }}>XX</ToggleButton>
              </ToggleButtonGroup>
            </Box>
            <TextField
              label="首攻（可选）"
              placeholder="如 西:S5 或留空"
              value={contractDialogForm.openingLead}
              onChange={(e) => setContractDialogForm({ ...contractDialogForm, openingLead: e.target.value })}
              size="small"
              fullWidth
              helperText="格式：位置:花色牌面，如 西:S5。留空则由AI自动决策"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setContractDialogOpen(false)}>取消</Button>
          <Button onClick={handleContractDialogConfirm} variant="contained">开始打牌</Button>
        </DialogActions>
      </Dialog>

      {/* 重新打牌 — 首攻确认对话框 */}
      <Dialog open={resetOpeningLeadDialogOpen} onClose={() => setResetOpeningLeadDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: '1rem' }}>重新打牌 — 首攻牌</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mt: 1 }}>
            {imageOpeningLead ? (
              <Typography variant="body2" color="text.secondary">
                当前首攻: <strong>{imageOpeningLead}</strong>
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                当前无首攻（AI 决定）
              </Typography>
            )}
            <TextField
              label="修改首攻"
              value={resetOpeningLeadValue}
              onChange={(e) => setResetOpeningLeadValue(e.target.value)}
              size="small"
              fullWidth
              placeholder="如 西:S5，留空则清除"
              helperText="留空 + 点击「清除」= AI自行决定首攻"
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between', px: 3, pb: 2 }}>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button onClick={() => handleResetOpeningLeadConfirm('clear')} color="error" variant="outlined" size="small">
              清除
            </Button>
            <Button onClick={() => handleResetOpeningLeadConfirm('edit')} color="primary" variant="outlined" size="small">
              修改
            </Button>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button onClick={() => { setResetOpeningLeadDialogOpen(false) }} size="small">取消</Button>
            <Button onClick={() => handleResetOpeningLeadConfirm('keep')} variant="contained" size="small">
              保留
            </Button>
          </Box>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

function App({ darkMode, onToggleDarkMode }) {
  return (
    <GameProvider>
      <BiddingProvider>
        <PlayProvider>
          <AppShell darkMode={darkMode} onToggleDarkMode={onToggleDarkMode} />
        </PlayProvider>
      </BiddingProvider>
    </GameProvider>
  )
}


export default App
