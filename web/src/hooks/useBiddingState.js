import { useState, useCallback } from 'react'

function useBiddingState() {
  const [biddingSequence, setBiddingSequence] = useState([])
  const [currentBidder, setCurrentBidder] = useState('南')
  const [bidSuggestion, setBidSuggestion] = useState(null)
  const [aiBiddingHistory, setAiBiddingHistory] = useState([])
  const [currentBiddingPosition, setCurrentBiddingPosition] = useState(null)
  const [selectedBiddingIndex, setSelectedBiddingIndex] = useState(-1)
  const [simpleDisplayMode, setSimpleDisplayMode] = useState(false)
  const [showBiddingControls, setShowBiddingControls] = useState(false)
  const [biddingStarted, setBiddingStarted] = useState(false)
  const [isNewDeal, setIsNewDeal] = useState(true)
  const [stopBidding, setStopBidding] = useState(false)
  const [passedAIPositions, setPassedAIPositions] = useState(new Set())
  const [biddingStartTime, setBiddingStartTime] = useState(null)
  const [biddingTotalTime, setBiddingTotalTime] = useState(null)
  const [customBidMeaning, setCustomBidMeaning] = useState('')
  const [suggestionLoading, setSuggestionLoading] = useState(false)

  const isBiddingComplete = useCallback(() => {
    if (biddingSequence.length < 4) return false
    
    const lastFour = biddingSequence.slice(-4)
    return lastFour.every(bid => bid.bid === 'pass')
  }, [biddingSequence])

  const resetBidding = useCallback((newDealer) => {
    setDealer(newDealer)
    setCurrentBidder(newDealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setIsNewDeal(true)
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

  const toggleStopBidding = useCallback(() => {
    setStopBidding(prev => !prev)
  }, [])

  const startBidding = useCallback(() => {
    setBiddingStarted(true)
    setIsNewDeal(false)
    setBiddingStartTime(Date.now())
  }, [])

  return {
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
    showBiddingControls,
    setShowBiddingControls,
    biddingStarted,
    setBiddingStarted,
    isNewDeal,
    setIsNewDeal,
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
    resetBidding,
    toggleStopBidding,
    startBidding,
  }
}

export default useBiddingState
