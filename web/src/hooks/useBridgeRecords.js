import { useState, useCallback, useRef } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

// 把完整记录提炼为轻量摘要，仅供历史列表展示，不携带牌张/play 全量等大字段
function indexify(r) {
  const b = r.board || {}
  const p = r.play
  const play = p ? {
    state: !!p.state, tricks: !!p.tricks,
    declarer_tricks: p.declarer_tricks, defender_tricks: p.defender_tricks,
  } : null
  return {
    id: r.id, timestamp: r.timestamp, type: r.type,
    note: r.note, sourceRecordId: r.sourceRecordId,
    dealer: b.dealer || r.dealer,
    finalContract: r.finalContract || b.contract,
    biddingSequence: r.biddingSequence || b.bidding_sequence,
    board: {
      contract: b.contract, dealer: b.dealer,
      bidding_sequence: b.bidding_sequence, opening_lead: b.opening_lead,
    },
    play,
  }
}

function useBridgeRecords() {
  const [records, setRecords] = useState([])
  const [historyDialogOpen, setHistoryDialogOpenRaw] = useState(false)
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false)
  const [editingRecordId, setEditingRecordId] = useState(null)
  const [editingNote, setEditingNote] = useState('')
  const [selectedRecordIds, setSelectedRecordIds] = useState(new Set())
  const lastSyncedRef = useRef('')  // 上次同步的 JSON 指纹，避免重复写

  // ── 服务器备份同步（debounce 2s）──
  const syncTimerRef = useRef(null)
  const syncBackupToServer = useCallback((recordsToSync) => {
    if (!recordsToSync || recordsToSync.length === 0) return
    const fingerprint = JSON.stringify(recordsToSync.map(r => r.id))
    if (fingerprint === lastSyncedRef.current) return  // 指纹未变，跳过
    lastSyncedRef.current = fingerprint

    if (syncTimerRef.current) clearTimeout(syncTimerRef.current)
    syncTimerRef.current = setTimeout(() => {
      fetch(`${API_BASE}/api/records/backup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ records: recordsToSync }),
      }).then(r => r.json()).then(data => {
        if (data.success) console.log('[备份] 已同步', data.count, '条记录到服务器')
      }).catch(err => {
        console.warn('[备份] 同步失败（服务器可能未启动）:', err.message)
      })
    }, 2000)
  }, [])

  // 从后端备份文件加载记录（不常驻内存）
  const loadRecords = useCallback(() => {
    // 历史记录一律以后端备份文件为准，前端不常驻、不写 localStorage
    fetch(`${API_BASE}/api/records/index`)
      .then(r => r.json())
      .then(data => {
        if (data.success && data.records && data.records.length > 0) {
          console.log('[记录] 从服务器加载', data.records.length, '条记录')
          setRecords(data.records)
        } else {
          // 服务端无记录，尝试迁移旧本地格式作为首次兜底
          tryMigrateOldFormat()
        }
      })
      .catch(() => {
        // 服务器不可用，尝试迁移旧本地格式作为兜底
        tryMigrateOldFormat()
      })

      // 辅助：迁移旧格式
      const tryMigrateOldFormat = () => {
        const oldBidding = localStorage.getItem('bridge_bidding_records')
        if (!oldBidding) {
          setRecords([])
          return
        }
        const oldRecords = JSON.parse(oldBidding)
        const migrated = oldRecords.map(r => {
          let derivedContract = r.finalContract || r.contract || null
          if (!derivedContract && r.biddingSequence && r.biddingSequence.length > 0) {
            const nonPassBids = r.biddingSequence.filter(b => b.bid && b.bid !== 'pass' && b.bid !== 'Pass')
            if (nonPassBids.length > 0) {
              const lastBid = nonPassBids[nonPassBids.length - 1]
              const bid = lastBid.bid
              let level, suit, contractPosition, isDouble = false, isRedouble = false
              if (bid === 'X') {
                const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid !== 'X' && b.bid !== 'XX')
                if (targetBids.length > 0) {
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
                if (doubleBids.length > 0) {
                  const doubleBid = doubleBids[doubleBids.length - 1]
                  const originalBids = nonPassBids.slice(0, nonPassBids.indexOf(doubleBid)).filter(b => b.bid !== 'X' && b.bid !== 'XX')
                  if (originalBids.length > 0) {
                    const originalBid = originalBids[originalBids.length - 1]
                    const match = originalBid.bid.match(/^(\d)([♠♥♦♣SHDC]|NT)$/i)
                    if (match) {
                      level = parseInt(match[1])
                      suit = match[2].toUpperCase() === 'NT' ? 'NT' : match[2].toUpperCase()
                      contractPosition = lastBid.position
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
                derivedContract = { level, suit, declarer: contractPosition, partnership: (contractPosition === '南' || contractPosition === '北') ? '南北' : '东西', doubled: isDouble, redoubled: isRedouble }
              }
            }
          }
          return {
            id: r.id, timestamp: r.timestamp, type: 'bidding_only',
            board: { hands: r.hands || {}, bidding_sequence: r.biddingSequence || [], contract: derivedContract, dealer: r.dealer || null, game_mode: r.gameMode || null, position_roles: r.playerRoles || {} },
            bidding: { ai_bidding_history: r.aiBiddingHistory || [], deal_system: r.dealSystem || 'jf' },
            play: null, note: r.note || '',
          }
        })
        setRecords(migrated.map(indexify))
        syncBackupToServer(migrated)
      }
  }, [syncBackupToServer])

  // 按 id 从后端取完整记录（点击加载/复盘时用）
  const fetchFullRecord = useCallback(async (id) => {
    try {
      const res = await fetch(`${API_BASE}/api/records/full/${encodeURIComponent(id)}`)
      const data = await res.json()
      return data.success ? data.record : null
    } catch (e) {
      console.warn('[加载] 获取完整记录失败:', e)
      return null
    }
  }, [])

  // 按 id 集合批量取完整记录（导出时用）
  const fetchFullRecords = useCallback(async (ids) => {
    try {
      const res = await fetch(`${API_BASE}/api/records/export`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      })
      const data = await res.json()
      return data.success ? (data.records || []) : []
    } catch (e) {
      console.warn('[导出] 获取完整记录失败:', e)
      return []
    }
  }, [])

  const saveRecord = useCallback((record) => {
    console.log('[saveRecord] 开始保存, type:', record.type, 'sourceRecordId:', record.sourceRecordId, 'id:', record.id)
    // 完整记录只落盘到后端（按 id upsert），前端仅保留轻量摘要
    fetch(`${API_BASE}/api/records/upsert`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record }),
    }).catch(err => console.warn('[保存] 同步失败（后端可能未启动）:', err.message))

    const summary = indexify(record)
    setRecords(prev => {
      try {
        const sid = record.sourceRecordId
        let existingIndex = -1
        if (sid) {
          existingIndex = prev.findIndex(r => (r.id === sid) || (r.sourceRecordId === sid))
        }
        let next
        if (existingIndex >= 0) {
          next = [...prev]
          next[existingIndex] = { ...summary, id: prev[existingIndex].id }
        } else {
          next = [summary, ...prev.filter(r => String(r.id) !== String(record.id))]
        }
        return next.slice(0, 200)
      } catch (err) {
        console.error('[saveRecord] 更新索引失败:', err)
        return prev
      }
    })
  }, [])

  const deleteRecord = useCallback((id) => {
    setRecords(prev => prev.filter(r => String(r.id) !== String(id)))
    fetch(`${API_BASE}/api/records/delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [id] }),
    }).catch(err => console.warn('[删除] 同步失败:', err.message))
  }, [])

  const deleteRecords = useCallback((ids) => {
    const idsSet = new Set(ids.map(String))
    setRecords(prev => prev.filter(r => !idsSet.has(String(r.id))))
    setSelectedRecordIds(new Set())
    fetch(`${API_BASE}/api/records/delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    }).catch(err => console.warn('[删除] 同步失败:', err.message))
  }, [])

  const updateRecordNote = useCallback((id, note) => {
    setRecords(prev => prev.map(r => String(r.id) === String(id) ? { ...r, note } : r))
    fetch(`${API_BASE}/api/records/note`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, note }),
    }).catch(err => console.warn('[注释] 同步失败:', err.message))
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedRecordIds(prev => {
      if (prev.size === records.length) {
        return new Set()
      }
      return new Set(records.map(r => r.id))
    })
  }, [records])

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
        // 逐条 upsert 到后端（后端按 id 去重合并），成功后刷新摘要索引
        const requests = importedRecords.map(rec =>
          fetch(`${API_BASE}/api/records/upsert`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record: rec }),
          })
        )
        Promise.all(requests)
          .then(() => loadRecords())
          .catch(err => console.error('导入记录失败:', err))
      } catch (err) {
        console.error('导入记录失败:', err)
      }
    }
    reader.readAsText(file)
    if (event.target) event.target.value = ''
    return { success: true }
  }, [loadRecords])

  // 历史对话框：打开时按需从后端加载，关闭时释放记录，避免常驻内存
  const setHistoryDialogOpen = useCallback((open) => {
    setHistoryDialogOpenRaw(open)
    if (open) {
      loadRecords()
    } else {
      setRecords([])
    }
  }, [loadRecords])

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
    fetchFullRecord,
    fetchFullRecords,
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
