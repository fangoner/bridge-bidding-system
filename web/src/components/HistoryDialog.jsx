import { useState, useCallback, useEffect, memo } from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  List, ListItem, Box, Typography, Button, Checkbox, Divider, TextField,
} from '@mui/material'

// 历史记录列表项，memo化
const RecordItem = memo(function RecordItem({ record, isSelected, showDivider, onToggle }) {
  const biddingSeq = record.board?.bidding_sequence || record.biddingSequence || []
  const biddingStr = Array.isArray(biddingSeq)
    ? biddingSeq.map(b => `(${b.position})${b.bid}`).join('-') || '-'
    : (typeof biddingSeq === 'string' ? biddingSeq : '-')
  const hasPlay = !!(record.play?.state || record.play?.tricks)
  const contract = record.board?.contract || record.finalContract
  const dealer = record.board?.dealer || record.dealer
  const openingLead = record.board?.opening_lead || null

  return (
    <Box>
      {showDivider && <Divider />}
      <ListItem
        alignItems="flex-start"
        sx={{
          flexDirection: 'column',
          bgcolor: isSelected ? 'action.selected' : 'inherit',
          borderRadius: 1
        }}
        onClick={() => onToggle(record.id)}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
          <Checkbox
            checked={isSelected}
            size="small"
            sx={{ mt: 0.5 }}
            onClick={(e) => e.stopPropagation()}
            onChange={() => onToggle(record.id)}
          />
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
              <Typography variant="subtitle2">{record.timestamp}</Typography>
              <Typography variant="body2" color="text.secondary">
                {hasPlay
                  ? (record.type === 'play_in_progress' ? '打牌进行中' : '打牌完成')
                  : record.type === 'bidding_in_progress' ? '叫牌进行中' : '仅叫牌完成'}
                {' | '}发牌人: {dealer}家
              </Typography>
            </Box>
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2">
                <strong>定约:</strong>{' '}
                {contract
                  ? `${contract.level}${contract.suit}${contract.redoubled || contract.isRedouble ? 'XX' : contract.doubled || contract.isDouble ? 'X' : ''} (${contract.partnership} - ${contract.declarer}家)`
                  : '全部Pass'}
                {openingLead && (
                  <Box component="span" sx={{ ml: 2, color: 'warning.main', fontWeight: 500 }}>
                    首攻: {openingLead}
                  </Box>
                )}
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                <strong>叫牌序列:</strong> {biddingStr}
              </Typography>
              {record.play && (
                <Typography variant="body2" sx={{ mt: 0.5, color: 'primary.main' }}>
                  <strong>打牌结果:</strong>{' '}
                  {record.play.declarer_tricks >= (contract?.level || 0) + 6
                    ? '完成'
                    : `宕${(contract?.level || 0) + 6 - record.play.declarer_tricks}`}
                  {' '}({record.play.declarer_tricks}:{record.play.defender_tricks})
                </Typography>
              )}
              {record.note && (
                <Typography variant="body2" sx={{ mt: 0.5, color: '#666' }}>
                  <strong>注释:</strong> {record.note}
                </Typography>
              )}
            </Box>
          </Box>
        </Box>
      </ListItem>
    </Box>
  )
})

function HistoryDialog({
  open,
  onClose,
  records,
  onLoad,
  onDelete,
  onExport,
  onImport,
  onUpdateNote,
  onError,
}) {
  const [selectedIds, setSelectedIds] = useState(new Set())
  // 每次打开对话框清除上次选中
  useEffect(() => {
    if (open) setSelectedIds(new Set())
  }, [open])
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editingNote, setEditingNote] = useState('')

  const toggleSelection = useCallback((id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setSelectedIds(prev => {
      if (prev.size === records.length) return new Set()
      return new Set(records.map(r => r.id))
    })
  }, [records])

  const handleDelete = useCallback(() => {
    const selected = records.filter(r => selectedIds.has(r.id))
    const withNotes = selected.filter(r => r.note && r.note.trim() !== '')
    if (withNotes.length > 0) {
      if (!window.confirm(`选中的记录中有 ${withNotes.length} 条包含注释，确定要删除吗？`)) return
    }
    onDelete(Array.from(selectedIds))
    setSelectedIds(new Set())
  }, [records, selectedIds, onDelete])

  const handleLoad = useCallback(() => {
    if (selectedIds.size !== 1) return
    const record = records.find(r => selectedIds.has(r.id))
    if (record) {
      onLoad(record)
      onClose()
    }
  }, [records, selectedIds, onLoad, onClose])

  const handleExport = useCallback(() => {
    const toExport = selectedIds.size > 0 ? records.filter(r => selectedIds.has(r.id)) : records
    if (toExport.length === 0) {
      onError('没有可导出的记录')
      return
    }
    onExport(toExport)
  }, [records, selectedIds, onExport, onError])

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            牌局历史记录
            {records.length > 0 && (
              <Button size="small" onClick={toggleAll}>
                {selectedIds.size === records.length ? '取消全选' : '全选'}
              </Button>
            )}
          </Box>
        </DialogTitle>
        <DialogContent dividers>
          {records.length === 0 ? (
            <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
              暂无历史记录
            </Typography>
          ) : (
            <List>
              {records.map((record, index) => (
                <RecordItem
                  key={record.id}
                  record={record}
                  isSelected={selectedIds.has(record.id)}
                  showDivider={index > 0}
                  onToggle={toggleSelection}
                />
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Button size="small" disabled={selectedIds.size !== 1} onClick={handleLoad}>加载</Button>
          <Button size="small" disabled={selectedIds.size !== 1} onClick={() => {
            const record = records.find(r => selectedIds.has(r.id))
            if (record) {
              setEditingId(record.id)
              setEditingNote(record.note || '')
              setEditDialogOpen(true)
            }
          }}>编辑注释</Button>
          <Button size="small" color="error" disabled={selectedIds.size === 0} onClick={handleDelete}>
            删除{selectedIds.size > 0 && ` (${selectedIds.size})`}
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button component="label" size="small">
            导入
            <input type="file" accept=".json" hidden onChange={onImport} />
          </Button>
          <Button onClick={handleExport} disabled={records.length === 0} size="small">
            导出{selectedIds.size > 0 && ` (${selectedIds.size})`}
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>编辑注释</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus margin="dense" label="注释内容" fullWidth multiline rows={4}
            value={editingNote}
            onChange={(e) => setEditingNote(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>取消</Button>
          <Button onClick={() => { onUpdateNote(editingId, editingNote); setEditDialogOpen(false) }} variant="contained">
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default HistoryDialog
