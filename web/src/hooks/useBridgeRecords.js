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
            const lastBid = [...r.biddingSequence].reverse().find(b => b.bid && b.bid !== 'pass' && b.bid !== 'Pass')
            if (lastBid) {
              const bid = lastBid.bid
              const match = bid.match(/^(\d)([♠♥♦♣NT]|NT)$/)
              if (match) {
                derivedContract = {
                  level: parseInt(match[1]),
                  suit: match[2] === 'NT' ? 'NT' : match[2],
                  declarer: lastBid.position,
                  partnership: (lastBid.position === '南' || lastBid.position === '北') ? '南北' : '东西',
                  doubled: false,
                  redoubled: false,
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
              human_position: r.humanPosition || null,
              player_roles: r.playerRoles || {},
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
    setRecords(prev => {
      try {
        let newRecords
        
        // 如果有 sourceRecordId，优先查找并覆盖该记录
        if (record.sourceRecordId) {
          const existingIndex = prev.findIndex(r => 
            r.id === record.sourceRecordId || r.sourceRecordId === record.sourceRecordId
          )
          if (existingIndex >= 0) {
            newRecords = [...prev]
            newRecords[existingIndex] = { ...record, id: prev[existingIndex].id }
          } else {
            newRecords = [record, ...prev]
          }
        } else {
          // 没有sourceRecordId时，始终创建新记录
          newRecords = [record, ...prev]
        }
        
        newRecords = newRecords.slice(0, 100)
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('保存记录失败:', err)
        return prev
      }
    })
  }, [])

  const deleteRecord = useCallback((id) => {
    setRecords(prev => {
      try {
        const newRecords = prev.filter(r => r.id !== id)
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('删除记录失败:', err)
        return prev
      }
    })
  }, [])

  const deleteRecords = useCallback((ids) => {
    setRecords(prev => {
      try {
        const idsSet = new Set(ids)
        const newRecords = prev.filter(r => !idsSet.has(r.id))
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('批量删除记录失败:', err)
        return prev
      }
    })
    setSelectedRecordIds(new Set())
  }, [])

  const updateRecordNote = useCallback((id, note) => {
    setRecords(prev => {
      try {
        const newRecords = prev.map(r =>
          r.id === id ? { ...r, note } : r
        )
        localStorage.setItem(BRIDGE_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('更新注释失败:', err)
        return prev
      }
    })
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
