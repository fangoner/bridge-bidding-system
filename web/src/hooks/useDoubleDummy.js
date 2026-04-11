import { useState, useCallback } from 'react'
import { doubleDummyAnalysis } from '../services/api'

function useDoubleDummy() {
  const [showDoubleDummy, setShowDoubleDummy] = useState(false)
  const [doubleDummyResult, setDoubleDummyResult] = useState(null)
  const [doubleDummyLoading, setDoubleDummyLoading] = useState(false)

  const toggleDoubleDummy = useCallback((value) => {
    setShowDoubleDummy(value)
  }, [])

  const analyzeDoubleDummy = useCallback(async (hands, strain) => {
    setDoubleDummyLoading(true)
    try {
      const result = await doubleDummyAnalysis(hands, strain)
      setDoubleDummyResult(result)
      return result
    } catch (err) {
      console.error('双明手分析失败:', err)
      return null
    } finally {
      setDoubleDummyLoading(false)
    }
  }, [])

  const resetDoubleDummy = useCallback(() => {
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setDoubleDummyLoading(false)
  }, [])

  return {
    showDoubleDummy,
    setShowDoubleDummy,
    doubleDummyResult,
    setDoubleDummyResult,
    doubleDummyLoading,
    setDoubleDummyLoading,
    toggleDoubleDummy,
    analyzeDoubleDummy,
    resetDoubleDummy,
  }
}

export default useDoubleDummy
