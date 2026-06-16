import { useState, useCallback } from 'react'

const BRIDGE_RECORDS_KEY = 'bridge_records'

function useBridgeRecords() {
  const [records, setRecords] = useState([])
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false)
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false)
  const [editingRecordId, setEditingRecordId] = useState(null)
  const [editingNote, setEditingNote] = useState('')
  const [selectedRecordIds, setSelectedRecordIds] = useState(new Set())

  // 从 localStorage 加载记录，兼容旧格式
  const loadRecords = useCallback(() => {
    try {
      // 1. 尝试加载新格式
      const newRecords = localStorage.getItem(BRIDGE_RECORDS_KEY)
      if (newRecords) {
        setRecords(JSON.parse(newRecords))
        return
      }

      // 2. 没有新格式，尝试迁移旧格式（叫牌记录）
      const oldBidding = localStorage.getItem('bridge_bidding_records')
      if (oldBidding) {
        const oldRecords = JSON.parse(oldBidding)
        const migrated = oldRecords.map(r => {
          // 从 biddingSequence 推导定约（最后一条非pass的叫品）
          let derivedContract = r.finalContract || r.contract || null
          if (!derivedContract && r.biddingSequence && r.biddingSequence.length > 0) {
            const nonPassBids = r.biddingSequence.filter(b => b.bid && b.bid !== 'pass' && b.bid !== 'Pass')
            if (nonPassBids.length > 0) {
              const lastBid = nonPassBids[nonPassBids.length - 1]
              const bid = lastBid.bid
              let level, suit, contractPosition, isDouble = false, isRedouble = false

              if (bid === 'X') {
                const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid !== 'X' && b.bid !== 'XX')
                if (targetBids.length === 0) { /* skip */ }
                else {
                  const targetBid = targetBids[targetBids.length - 1]
                  const match = targetBid.bid.match(/^(\d)([♠♥♦♣SHDC]|NT)$/i)
                  if (match) {
                    level = parseInt(match[1])
                    suit = match[2].toUpperCase() === 'NT' ? 'NT' : match[2].toUpperCase()
                    contractPosition = targetBid.position
                    isDouble = true
                  }
                }
              } else if (bid === 'XX') {
                const doubleBids = nonPassBids.slice(0, -1).filter(b => b.bid === 'X')
                if (doubleBids.length === 0) { /* skip */ }
                else {
                  const doubleBid = doubleBids[doubleBids.length - 1]
                  const originalBids = nonPassBids.slice(0, nonPassBids.indexOf(doubleBid)).filter(b => b.bid !== 'X' && b.bid !== 'XX')
                  if (originalBids.length > 0) {
                    const originalBid = originalBids[originalBids.length - 1]
                    const match = originalBid.bid.match(/^(\d)([♠♥♦♣SHDC]|NT)$/i)
                    if (match) {
                      level = parseInt(match[1])
                      suit = match[2].toUpperCase() === 'NT' ? 'NT' : match[2].toUpperCase()
                      contractPosition = lastBid.position  // redoubler is on declaring side
                      isDouble = true
                      isRedouble = true
                    }
                  }
                }
              } else {
                const match = bid.match(/^(\d)([♠♥♦♣SHDC]|NT)$/i)
                if (match) {
                  level = parseInt(match[1])
                  suit = match[2].toUpperCase() === 'NT' ? 'NT' : match[2].toUpperCase()
                  contractPosition = lastBid.position
                }
              }

              if (level && suit) {
                derivedContract = {
                  level,
                  suit,
                  declarer: contractPosition,
                  partnership: (contractPosition === '南' || contractPosition === '北') ? '南北' : '东西',
                  doubled: isDouble,
                  redoubled: isRedouble,
                }
              }
            }
          }
          return {
            id: r.id,
            timestamp: r.timestamp,
            type: 'bidding_only',
            board: {
              hands: r.hands || {},
              bidding_sequence: r.biddingSequence || [],
              contract: derivedContract,
              dealer: r.dealer || null,
              game_mode: r.gameMode || null,
              position_roles: r.playerRoles || {},
            },
            bidding: {
              ai_bidding_history: r.aiBiddingHistory || [],
              deal_system: r.dealSystem || 'jf',
            },
            play: null,
            note: r.note || '',
          }
        })
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(migrated))
        setRecords(migrated)
        return
      }

      setRecords([])
    } catch (err) {
      console.error('加载记录失败:', err)
      setRecords([])
    }
  }, [])

  // 判断两条记录是否是同一副牌（基于手牌和叫牌序列）
  const isSameBoard = (a, b) => {
    const aHands = JSON.stringify(a.board?.hands || a.hands || {})
    const bHands = JSON.stringify(b.board?.hands || b.hands || {})
    const aBidding = JSON.stringify(a.board?.bidding_sequence || a.biddingSequence || [])
    const bBidding = JSON.stringify(b.board?.bidding_sequence || b.biddingSequence || [])
    return aHands === bHands && aBidding === bBidding
  }

  const saveRecord = useCallback((record) => {
    console.log('[saveRecord] 开始保存, type:', record.type, 'sourceRecordId:', record.sourceRecordId, 'id:', record.id)
    setRecords(prev => {
      try {
        let newRecords
        if (record.sourceRecordId) {
          const existingIndex = prev.findIndex(r =>
            r.id === record.sourceRecordId || r.sourceRecordId === record.sourceRecordId
          )
          console.log('[saveRecord] 查找sourceRecordId, existingIndex:', existingIndex, 'prev count:', prev.length)
          if (existingIndex >= 0) {
            newRecords = [...prev]
            newRecords[existingIndex] = { ...record, id: prev[existingIndex].id }
          } else {
            newRecords = [record, ...prev]
          }
        } else {
          newRecords = [record, ...prev]
        }
        newRecords = newRecords.slice(0, 100)

        // 在 updater 内直接写 localStorage（避免 React 18 并发模式下 resultRecords 未赋值）
        try {
          localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(newRecords))
          console.log('[saveRecord] 持久化成功, count:', newRecords.length)
        } catch (err) {
          if (err.name === 'QuotaExceededError' && newRecords.length > 10) {
            console.warn('[saveRecord] localStorage quota 超限，自动清理旧记录')
            const trimmed = newRecords.slice(0, newRecords.length - 10)
            try {
              localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(trimmed))
              return trimmed
            } catch (e2) {
              console.error('[saveRecord] 清理后仍无法保存:', e2)
            }
          } else {
            console.error('[saveRecord] 持久化记录失败:', err)
          }
        }

        return newRecords
      } catch (err) {
        console.error('[saveRecord] 保存记录失败:', err)
        return prev
      }
    })
  }, [])

  const deleteRecord = useCallback((id) => {
    let resultRecords
    setRecords(prev => {
      try {
        const newRecords = prev.filter(r => r.id !== id)
        resultRecords = newRecords
        return newRecords
      } catch (err) {
        console.error('删除记录失败:', err)
        resultRecords = prev
        return prev
      }
    })
    if (resultRecords) {
      try {
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(resultRecords))
      } catch (err) {
        console.error('持久化记录失败:', err)
      }
    }
  }, [])

  const deleteRecords = useCallback((ids) => {
    let resultRecords
    setRecords(prev => {
      try {
        const idsSet = new Set(ids)
        const newRecords = prev.filter(r => !idsSet.has(r.id))
        resultRecords = newRecords
        return newRecords
      } catch (err) {
        console.error('批量删除记录失败:', err)
        resultRecords = prev
        return prev
      }
    })
    setSelectedRecordIds(new Set())
    if (resultRecords) {
      try {
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(resultRecords))
      } catch (err) {
        console.error('持久化记录失败:', err)
      }
    }
  }, [])

  const updateRecordNote = useCallback((id, note) => {
    let resultRecords
    setRecords(prev => {
      try {
        const newRecords = prev.map(r =>
          r.id === id ? { ...r, note } : r
        )
        resultRecords = newRecords
        return newRecords
      } catch (err) {
        console.error('更新注释失败:', err)
        resultRecords = prev
        return prev
      }
    })
    if (resultRecords) {
      try {
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(resultRecords))
      } catch (err) {
        console.error('持久化记录失败:', err)
      }
    }
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedRecordIds(prev => {
      if (prev.size === records.length) {
        return new Set()
      }
      return new Set(records.map(r => r.id))
    })
  }, [records.length])

  const toggleRecordSelection = useCallback((id) => {
    setSelectedRecordIds(prev => {
      const newSelected = new Set(prev)
      if (newSelected.has(id)) {
        newSelected.delete(id)
      } else {
        newSelected.add(id)
      }
      return newSelected
    })
  }, [])

  const exportRecords = useCallback(() => {
    try {
      const recordsToExport = selectedRecordIds.size > 0
        ? records.filter(r => selectedRecordIds.has(r.id))
        : records

      if (recordsToExport.length === 0) {
        return { success: false, error: '没有可导出的记录' }
      }

      const exportData = {
        version: '2.0',
        exportDate: new Date().toISOString(),
        records: recordsToExport
      }
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
      return { success: true }
    } catch (err) {
      console.error('导出记录失败:', err)
      return { success: false, error: '导出记录失败' }
    }
  }, [records, selectedRecordIds])

  const importRecords = useCallback((event) => {
    const file = event.target.files?.[0]
    if (!file) return { success: false, error: '未选择文件' }

    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const importData = JSON.parse(e.target.result)
        if (!importData.records || !Array.isArray(importData.records)) {
          console.error('无效的记录文件格式')
          return
        }

        const importedRecords = importData.records
        setRecords(prev => {
          // 合并后按牌局去重：同一手牌+叫牌序列保留最新的
          const merged = [...importedRecords, ...prev]
          const unique = []
          const seen = new Set()
          
          for (const record of merged) {
            const key = JSON.stringify(record.board?.hands || record.hands || {}) + 
                        JSON.stringify(record.board?.bidding_sequence || record.biddingSequence || [])
            if (!seen.has(key)) {
              seen.add(key)
              unique.push(record)
            }
          }
          
          const mergedRecords = unique.slice(0, 100)
          localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(mergedRecords))
          return mergedRecords
        })
      } catch (err) {
        console.error('导入记录失败:', err)
      }
    }
    reader.readAsText(file)
    if (event.target) event.target.value = ''
    return { success: true }
  }, [])

  return {
    records,
    setRecords,
    historyDialogOpen,
    setHistoryDialogOpen,
    editNoteDialogOpen,
    setEditNoteDialogOpen,
    editingRecordId,
    setEditingRecordId,
    editingNote,
    setEditingNote,
    selectedRecordIds,
    setSelectedRecordIds,
    loadRecords,
    saveRecord,
    deleteRecord,
    deleteRecords,
    updateRecordNote,
    toggleSelectAll,
    toggleRecordSelection,
    exportRecords,
    importRecords,
  }
}

export default useBridgeRecords
