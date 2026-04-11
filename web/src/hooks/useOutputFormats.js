import { useState, useCallback } from 'react'
import { getOutputFormats, analyzeContract } from '../services/api'

function useOutputFormats() {
  const [outputFormats, setOutputFormats] = useState(null)
  const [outputFormatsLoading, setOutputFormatsLoading] = useState(false)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)
  const [showMoreFormats, setShowMoreFormats] = useState(false)

  const fetchOutputFormats = useCallback(async (hands, biddingSequence) => {
    setOutputFormatsLoading(true)
    try {
      const result = await getOutputFormats(hands, biddingSequence)
      setOutputFormats(result)
      return result
    } catch (err) {
      console.error('获取输出格式失败:', err)
      return null
    } finally {
      setOutputFormatsLoading(false)
    }
  }, [])

  const handleAnalyzeContract = useCallback(async (hands, contract, declarer) => {
    setAnalyzeLoading(true)
    try {
      const result = await analyzeContract(hands, contract, declarer)
      setAnalyzeResult(result)
      return result
    } catch (err) {
      console.error('检验定约失败:', err)
      return null
    } finally {
      setAnalyzeLoading(false)
    }
  }, [])

  const resetOutputFormats = useCallback(() => {
    setOutputFormats(null)
    setOutputFormatsLoading(false)
    setAnalyzeLoading(false)
    setAnalyzeResult(null)
    setShowMoreFormats(false)
  }, [])

  return {
    outputFormats,
    setOutputFormats,
    outputFormatsLoading,
    setOutputFormatsLoading,
    analyzeLoading,
    setAnalyzeLoading,
    analyzeResult,
    setAnalyzeResult,
    showMoreFormats,
    setShowMoreFormats,
    fetchOutputFormats,
    handleAnalyzeContract,
    resetOutputFormats,
  }
}

export default useOutputFormats
