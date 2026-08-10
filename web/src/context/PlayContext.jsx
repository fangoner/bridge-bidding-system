/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, useState } from 'react'

// Play 域：出牌/墩/明手/DD提示/打牌引擎相关状态
export const PlayContext = createContext(null)

export function usePlay() {
  const ctx = useContext(PlayContext)
  if (!ctx) {
    throw new Error('usePlay 必须在 <PlayProvider> 内部使用')
  }
  return ctx
}

const PLAY_ENGINE_KEY = 'bridge_play_engine'
const LLM_REVIEW_KEY = 'bridge_use_llm_review'

export function PlayProvider({ children }) {
  // ── 打牌核心状态 ──
  const [playState, setPlayState] = useState(null)
  const [playLoading, setPlayLoading] = useState(false)
  const [showPlayPanel, setShowPlayPanel] = useState(false)
  const [showPlayedCards, setShowPlayedCards] = useState(true)
  const [playCenterView, setPlayCenterView] = useState('play') // 'play'/'bidding'/'result'
  const [isPlayPaused, setIsPlayPaused] = useState(false)
  const [lastCompletedTrick, setLastCompletedTrick] = useState(null)
  const [aiPlayHistory, setAiPlayHistory] = useState([])
  const [selectedPlayRecord, setSelectedPlayRecord] = useState(null)
  const [playStarted, setPlayStarted] = useState(false)
  const [playInitiated, setPlayInitiated] = useState(false)
  const [loadedPlayRecord, setLoadedPlayRecord] = useState(null)
  const [reviewCursor, setReviewCursor] = useState(null) // null=非复盘, 0~51=第N张牌

  // ── DD 提示（牌桌 Tooltip）──
  const [showDDHints, setShowDDHints] = useState(() => {
    try { return localStorage.getItem('bridge_showDDHints') !== 'false' } catch { return true }
  })
  const [ddHints, setDDHints] = useState(null)
  const [ddHintsLoading, setDDHintsLoading] = useState(false)

  // ── 直接打牌对话框 ──
  const [contractDialogOpen, setContractDialogOpen] = useState(false)
  const [resetOpeningLeadDialogOpen, setResetOpeningLeadDialogOpen] = useState(false)
  const [directPlayContractInfo, setDirectPlayContractInfo] = useState(null)

  // ── 打牌引擎 ──
  const [playEngine, setPlayEngineState] = useState(() => {
    try {
      return localStorage.getItem(PLAY_ENGINE_KEY) || 'dd_alphamu_llm'
    } catch {
      return 'dd_alphamu_llm'
    }
  })

  // ── LLM 分组审查开关（DD-αμ-LLM 引擎内，默认关闭以与纯引擎对比）──
  const [useLlmReview, setUseLlmReview] = useState(() => {
    try { return localStorage.getItem(LLM_REVIEW_KEY) === 'true' } catch { return false }
  })

  // ── helper 闭包（保持引用稳定即可，暂不需要 useCallback）──
  const toggleDDHints = () => {
    setShowDDHints(prev => {
      const next = !prev
      try { localStorage.setItem('bridge_showDDHints', String(next)) } catch {/* empty */}
      return next
    })
  }
  const handlePlayEngineChange = (value) => {
    setPlayEngineState(value)
    try { localStorage.setItem(PLAY_ENGINE_KEY, value) } catch {/* empty */}
  }
  const handleLlmReviewChange = (value) => {
    setUseLlmReview(value)
    try { localStorage.setItem(LLM_REVIEW_KEY, String(value)) } catch {/* empty */}
  }

  const value = useMemo(
    () => ({
      playState, setPlayState,
      playLoading, setPlayLoading,
      showPlayPanel, setShowPlayPanel,
      showPlayedCards, setShowPlayedCards,
      playCenterView, setPlayCenterView,
      isPlayPaused, setIsPlayPaused,
      lastCompletedTrick, setLastCompletedTrick,
      aiPlayHistory, setAiPlayHistory,
      selectedPlayRecord, setSelectedPlayRecord,
      playStarted, setPlayStarted,
      playInitiated, setPlayInitiated,
      loadedPlayRecord, setLoadedPlayRecord,
      reviewCursor, setReviewCursor,
      showDDHints, setShowDDHints,
      ddHints, setDDHints,
      ddHintsLoading, setDDHintsLoading,
      toggleDDHints,
      contractDialogOpen, setContractDialogOpen,
      resetOpeningLeadDialogOpen, setResetOpeningLeadDialogOpen,
      directPlayContractInfo, setDirectPlayContractInfo,
      playEngine, setPlayEngineState,
      handlePlayEngineChange,
      useLlmReview, setUseLlmReview,
      handleLlmReviewChange,
    }),
    [
      playState, playLoading, showPlayPanel, showPlayedCards, playCenterView,
      isPlayPaused, lastCompletedTrick, aiPlayHistory, selectedPlayRecord,
      playStarted, playInitiated, loadedPlayRecord, reviewCursor,
      showDDHints, ddHints, ddHintsLoading,
      contractDialogOpen,
      resetOpeningLeadDialogOpen, directPlayContractInfo,
      playEngine, useLlmReview,
    ],
  )

  return <PlayContext.Provider value={value}>{children}</PlayContext.Provider>
}
