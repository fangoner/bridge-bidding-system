import { useState, useCallback, useMemo } from 'react'

function useBiddingState() {
  const [biddingSequence, setBiddingSequence] = useState([])
  const [currentBidder, setCurrentBidder] = useState('南')
  const [bidSuggestion, setBidSuggestion] = useState(null)
  const [aiBiddingHistory, setAiBiddingHistory] = useState([])
  const [currentBiddingPosition, setCurrentBiddingPosition] = useState(null)
  const [selectedBiddingIndex, setSelectedBiddingIndex] = useState(-1)
  const [simpleDisplayMode, setSimpleDisplayMode] = useState(false)
  const [biddingStarted, setBiddingStarted] = useState(false)
  const [stopBidding, setStopBidding] = useState(false)
  const [passedAIPositions, setPassedAIPositions] = useState(new Set())
  const [biddingStartTime, setBiddingStartTime] = useState(null)
  const [biddingTotalTime, setBiddingTotalTime] = useState(null)
  const [customBidMeaning, setCustomBidMeaning] = useState('')
  const [suggestionLoading, setSuggestionLoading] = useState(false)

  const isBiddingComplete = useCallback(() => {
    if (biddingSequence.length < 4) return false

    // 检查最后四个是否都是pass
    const lastFour = biddingSequence.slice(-4)
    if (lastFour.length === 4 && lastFour.every(b => b.bid === 'pass')) {
      return true
    }

    // 检查是否有3个连续的pass在第一个实质性叫品之后
    let hasRealBid = false
    for (let i = 0; i < biddingSequence.length; i++) {
      if (biddingSequence[i].bid !== 'pass') {
        hasRealBid = true
      }
      if (hasRealBid && i >= 2) {
        const lastThree = biddingSequence.slice(i - 2, i + 1)
        if (lastThree.every(b => b.bid === 'pass')) {
          return true
        }
      }
    }

    return false
  }, [biddingSequence])

  const initBiddingState = useCallback((newDealer) => {
    setCurrentBidder(newDealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setBiddingSequence([])
    setAiBiddingHistory([])
    setPassedAIPositions(new Set())
    setBiddingStartTime(null)
    setBiddingTotalTime(null)
    setCustomBidMeaning('')
    setBidSuggestion(null)
    setCurrentBiddingPosition(null)
    setSelectedBiddingIndex(-1)
  }, [])

  const toggleStopBiddingState = useCallback(() => {
    setStopBidding(prev => !prev)
  }, [])

  const markBiddingStarted = useCallback(() => {
    setBiddingStarted(true)
    setBiddingStartTime(Date.now())
  }, [])

  return useMemo(() => ({
    biddingSequence,
    setBiddingSequence,
    currentBidder,
    setCurrentBidder,
    bidSuggestion,
    setBidSuggestion,
    aiBiddingHistory,
    setAiBiddingHistory,
    currentBiddingPosition,
    setCurrentBiddingPosition,
    selectedBiddingIndex,
    setSelectedBiddingIndex,
    simpleDisplayMode,
    setSimpleDisplayMode,
    biddingStarted,
    setBiddingStarted,
    stopBidding,
    setStopBidding,
    passedAIPositions,
    setPassedAIPositions,
    biddingStartTime,
    setBiddingStartTime,
    biddingTotalTime,
    setBiddingTotalTime,
    customBidMeaning,
    setCustomBidMeaning,
    suggestionLoading,
    setSuggestionLoading,
    isBiddingComplete,
    initBiddingState,
    toggleStopBiddingState,
    markBiddingStarted,
  }), [
    biddingSequence,
    currentBidder,
    bidSuggestion,
    aiBiddingHistory,
    currentBiddingPosition,
    selectedBiddingIndex,
    simpleDisplayMode,
    biddingStarted,
    stopBidding,
    passedAIPositions,
    biddingStartTime,
    biddingTotalTime,
    customBidMeaning,
    suggestionLoading,
    isBiddingComplete,
    initBiddingState,
    toggleStopBiddingState,
    markBiddingStarted,
  ])
}

export default useBiddingState
