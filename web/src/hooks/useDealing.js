import { useCallback, useRef } from 'react'
import { dealCards, customDeal, imageDeal, triggerScreenshot, readClipboardDeal } from '../services/api'
import { BRIDGE_POSITIONS } from '../utils/position'
import { useGame } from '../context/GameContext'
import { useBidding } from '../context/BiddingContext'
import { usePlay } from '../context/PlayContext'

// 解析后端返回的叫牌序列字符串为 biddingSequence 数组
// 格式: "(北)pass-(东)pass-(南)1NT-(西)pass-..."
export function parseBiddingSequenceStr(biddingStr) {
  if (!biddingStr) return []
  const items = biddingStr.split('-').filter(s => s.trim())
  const result = items.map(item => {
    const match = item.trim().match(/^\(([^)]+)\)(.+)$/)
    if (match) {
      let bid = match[2]
      if (bid === '不叫' || bid === 'Pass' || bid === 'PASS') bid = 'pass'
      if (bid === '加倍' || bid === 'Double') bid = 'X'
      if (bid === '再加倍' || bid === 'Redouble') bid = 'XX'
      return { position: match[1], bid }
    }
    return null
  }).filter(Boolean)

  // 补齐或裁剪结束叫牌的pass：最后一个实质性叫品后必须恰好3个pass
  if (result.length > 0) {
    let lastSubstantiveIdx = -1
    for (let i = result.length - 1; i >= 0; i--) {
      if (result[i].bid !== 'pass') {
        lastSubstantiveIdx = i
        break
      }
    }
    if (lastSubstantiveIdx >= 0) {
      const trailingPasses = result.length - 1 - lastSubstantiveIdx
      if (trailingPasses > 3) {
        result.splice(lastSubstantiveIdx + 4)
      } else if (trailingPasses < 3) {
        const needed = 3 - trailingPasses
        const lastPos = result[result.length - 1].position
        const lastIdx = BRIDGE_POSITIONS.indexOf(lastPos)
        for (let i = 1; i <= needed; i++) {
          result.push({ position: BRIDGE_POSITIONS[(lastIdx + i) % 4], bid: 'pass' })
        }
      }
    }
  }
  return result
}

// 发牌流程 hook：封装发牌/自定义牌局/图片识别/截屏识别/清除手牌
// clearBiddingDraft 由调用方传入（依赖 BIDDING_DRAFT_KEY 等本地逻辑）
export function useDealing({ clearBiddingDraft }) {
  const {
    setHands,
    loading, setLoading,
    setError,
    setWarning,
    dealer, setDealer,
    setPositionRoles,
    setShowPartnerHand,
    setShowOpponentHands,
    setCurrentRecordId,
    setUseFallback,
    setReadonlyMode,
    setImageOpeningLead,
  } = useGame()

  const {
    setBiddingSequence,
    setBidSuggestion,
    setAiBiddingHistory,
    setCurrentBidder,
    setBiddingStarted,
    setStopBidding,
    setPassedAIPositions,
    setShowDoubleDummy,
    setDoubleDummyResult,
    setBiddingHistory,
    setHistoryIndex,
    setOutputFormats,
  } = useBidding()

  const {
    setShowPlayPanel,
    setPlayState,
    setAiPlayHistory,
    setIsPlayPaused,
    setLoadedPlayRecord,
    setLastCompletedTrick,
    setPlayStarted,
    setPlayInitiated,
    setDirectPlayContractInfo,
  } = usePlay()

  const screenshotCancelledRef = useRef(false)

  // 公共：识别到完整定约时构造 directPlayContractInfo
  const buildDirectPlayInfo = (data) => {
    if (data.contract_level && data.contract_suit && data.contract_declarer) {
      return {
        level: data.contract_level,
        suit: data.contract_suit,
        declarer: data.contract_declarer,
        isDouble: data.contract_doubled || false,
        isRedouble: data.contract_redoubled || false,
        partnership: ['南', '北'].includes(data.contract_declarer) ? '南北' : '东西',
        bid: `${data.contract_level}${data.contract_suit}${data.contract_doubled ? 'X' : ''}${data.contract_redoubled ? 'X' : ''}`,
      }
    }
    return null
  }

  // 公共：发牌/识别后重置牌局状态
  const resetGameState = useCallback((opts = {}) => {
    const { directPlayInfo = null, imageOpeningLead = null } = opts
    setBiddingSequence([])
    setBidSuggestion(null)
    setAiBiddingHistory([])
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setPassedAIPositions(new Set())
    setUseFallback(false)
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setPositionRoles({ '南': 'ai', '北': 'ai', '东': 'ai', '西': 'ai' })
    setBiddingHistory([])
    setHistoryIndex(-1)
    // 重置打牌相关状态
    setReadonlyMode(false)
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setIsPlayPaused(false)
    setLoadedPlayRecord(null)
    setLastCompletedTrick(null)
    setDirectPlayContractInfo(directPlayInfo)
    setImageOpeningLead(imageOpeningLead)
  }, [
    dealer, setBiddingSequence, setBidSuggestion, setAiBiddingHistory,
    setCurrentBidder, setBiddingStarted, setStopBidding, setPassedAIPositions,
    setUseFallback, setShowDoubleDummy, setDoubleDummyResult, setPositionRoles,
    setBiddingHistory, setHistoryIndex, setReadonlyMode, setShowPlayPanel,
    setPlayState, setAiPlayHistory, setIsPlayPaused, setLoadedPlayRecord,
    setLastCompletedTrick, setDirectPlayContractInfo, setImageOpeningLead,
  ])

  // 1. 发牌
  const handleDeal = useCallback(async (mode = 'free') => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    try {
      const data = await dealCards(mode)
      setHands(data.hands)
      resetGameState()
    } catch {
      setError('发牌失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setHands, resetGameState])

  // 2. 自定义牌局
  const handleCustomDeal = useCallback(async (inputText) => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    try {
      const data = await customDeal(inputText)
      if (data.success) {
        setHands(data.hands)
        resetGameState({ imageOpeningLead: data.opening_lead || null })
      } else {
        setError(data.message || '牌局解析失败')
      }
    } catch {
      setError('自定义牌局失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setHands, resetGameState])

  // 3. 图片识别牌局
  const handleImageDeal = useCallback(async (imageFile) => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    setWarning(null)
    try {
      const data = await imageDeal(imageFile)
      if (data.success) {
        setHands(data.hands)
        if (data.message && data.message !== '牌局已加载') setWarning(data.message)
        if (data.dealer) setDealer(data.dealer)
        const parsedBidding = parseBiddingSequenceStr(data.bidding_sequence)
        setBiddingSequence(parsedBidding)
        resetGameState({
          directPlayInfo: buildDirectPlayInfo(data),
          imageOpeningLead: data.opening_lead || null,
        })
        // dealer 已被更新，需要重新设置 currentBidder
        if (data.dealer) setCurrentBidder(data.dealer)
      } else {
        setError(data.message || '图片识别失败')
      }
    } catch {
      setError('图片识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setWarning,
      setHands, setDealer, setBiddingSequence, setCurrentBidder, resetGameState])

  // 4. 截屏识别牌局
  const handleScreenshotDeal = useCallback(async ({ setShowSettings = null } = {}) => {
    if (loading) return
    if (setShowSettings) setShowSettings(false)
    setLoading(true)
    screenshotCancelledRef.current = false
    setError('截屏已触发，请完成截图后等待识别...')
    setWarning(null)
    try {
      const result = await triggerScreenshot()
      if (!result.success) {
        setError(result.message || '触发截屏失败')
        setLoading(false)
        return
      }
      // 轮询读取剪贴板，每2秒一次，最多10次
      let data = null
      for (let i = 0; i < 10; i++) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        if (screenshotCancelledRef.current) {
          setLoading(false)
          return
        }
        try {
          const resp = await readClipboardDeal()
          if (resp.success) { data = resp; break }
        } catch {
          // 剪贴板还没有图片，继续等待
        }
        setError(`等待截屏中... (${i + 1}/10)`)
      }
      if (!data) {
        setError('截屏识别超时，请确保已完成截图并重试')
        setLoading(false)
        return
      }
      setHands(data.hands)
      if (data.message && data.message !== '识别成功') setWarning(data.message)
      if (data.dealer) setDealer(data.dealer)
      const parsedBidding = parseBiddingSequenceStr(data.bidding_sequence)
      setBiddingSequence(parsedBidding)
      resetGameState({
        directPlayInfo: buildDirectPlayInfo(data),
        imageOpeningLead: data.opening_lead || null,
      })
      if (data.dealer) setCurrentBidder(data.dealer)
      setError(null)
    } catch {
      setError('截屏识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [loading, setLoading, setError, setWarning, setHands, setDealer,
      setBiddingSequence, setCurrentBidder, resetGameState])

  // 5. 清除所有手牌
  const clearAllHands = useCallback(() => {
    clearBiddingDraft()
    setHands({
      '南': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '北': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '东': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '西': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    })
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setBiddingSequence([])
    setAiBiddingHistory([])
    setPassedAIPositions(new Set())
    setOutputFormats(null)
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setBiddingHistory([])
    setHistoryIndex(-1)
    setReadonlyMode(false)
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setIsPlayPaused(false)
    setPlayStarted(false)
    setPlayInitiated(false)
    setLoadedPlayRecord(null)
    setShowPartnerHand(false)
    setShowOpponentHands(false)
    setDirectPlayContractInfo(null)
    setImageOpeningLead(null)
  }, [clearBiddingDraft, dealer, setHands, setCurrentBidder, setBiddingStarted,
      setStopBidding, setBiddingSequence, setAiBiddingHistory, setPassedAIPositions,
      setOutputFormats, setShowDoubleDummy, setDoubleDummyResult, setBiddingHistory,
      setHistoryIndex, setReadonlyMode, setShowPlayPanel, setPlayState, setAiPlayHistory,
      setIsPlayPaused, setPlayStarted, setPlayInitiated, setLoadedPlayRecord,
      setShowPartnerHand, setShowOpponentHands, setDirectPlayContractInfo, setImageOpeningLead])

  // 取消截屏
  const cancelScreenshot = useCallback(() => {
    screenshotCancelledRef.current = true
  }, [])

  return {
    handleDeal,
    handleCustomDeal,
    handleImageDeal,
    handleScreenshotDeal,
    clearAllHands,
    cancelScreenshot,
    parseBiddingSequenceStr,
    screenshotCancelledRef,
  }
}

export default useDealing
