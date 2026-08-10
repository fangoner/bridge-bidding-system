import { useState, useCallback } from 'react'

const BIDDING_RECORDS_KEY = 'bridge_bidding_records'

function useBiddingRecords() {
  const [biddingRecords, setBiddingRecords] = useState([])
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false)
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false)
  const [editingRecordId, setEditingRecordId] = useState(null)
  const [editingNote, setEditingNote] = useState('')
  const [selectedRecordIds, setSelectedRecordIds] = useState(new Set())

  const loadBiddingRecords = useCallback(() => {
    try {
      const records = localStorage.getItem(BIDDING_RECORDS_KEY)
      if (records) {
        setBiddingRecords(JSON.parse(records))
      }
    } catch (err) {
      console.error('加载历史记录失败:', err)
    }
  }, [])

  const saveBiddingRecord = useCallback((record) => {
    setBiddingRecords(prev => {
      try {
        const newRecords = [record, ...prev].slice(0, 100)
        localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('保存记录失败:', err)
        return prev
      }
    })
  }, [])

  const deleteBiddingRecord = useCallback((id) => {
    setBiddingRecords(prev => {
      try {
        const newRecords = prev.filter(r => r.id !== id)
        localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('删除记录失败:', err)
        return prev
      }
    })
  }, [])

  const deleteBiddingRecords = useCallback((ids) => {
    setBiddingRecords(prev => {
      try {
        const idsSet = new Set(ids)
        const newRecords = prev.filter(r => !idsSet.has(r.id))
        localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('批量删除记录失败:', err)
        return prev
      }
    })
    setSelectedRecordIds(new Set())
  }, [])

  const updateRecordNote = useCallback((id, note) => {
    setBiddingRecords(prev => {
      try {
        const newRecords = prev.map(r => 
          r.id === id ? { ...r, note } : r
        )
        localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
        return newRecords
      } catch (err) {
        console.error('更新注释失败:', err)
        return prev
      }
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedRecordIds(prev => {
      if (prev.size === biddingRecords.length) {
        return new Set()
      }
      return new Set(biddingRecords.map(r => r.id))
    })
  }, [biddingRecords])

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
      // 无选中记录时导出全部，有选中记录时只导出选中的
      const recordsToExport = selectedRecordIds.size > 0 
        ? biddingRecords.filter(r => selectedRecordIds.has(r.id))
        : biddingRecords

      if (recordsToExport.length === 0) {
        return { success: false, error: '没有可导出的记录' }
      }

      const exportData = {
        version: '1.0',
        exportDate: new Date().toISOString(),
        records: recordsToExport
      }
      const dataStr = JSON.stringify(exportData, null, 2)
      const blob = new Blob([dataStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `bridge_bidding_records_${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      return { success: true }
    } catch (err) {
      console.error('导出记录失败:', err)
      return { success: false, error: '导出记录失败' }
    }
  }, [biddingRecords, selectedRecordIds])

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
        setBiddingRecords(prev => {
          const existingIds = new Set(prev.map(r => r.id))
          const newRecords = importedRecords.filter(r => !existingIds.has(r.id))
          const mergedRecords = [...newRecords, ...prev].slice(0, 100)
          localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(mergedRecords))
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
    biddingRecords,
    setBiddingRecords,
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
    loadBiddingRecords,
    saveBiddingRecord,
    deleteBiddingRecord,
    deleteBiddingRecords,
    updateRecordNote,
    toggleSelectAll,
    toggleRecordSelection,
    exportRecords,
    importRecords,
  }
}

export default useBiddingRecords
