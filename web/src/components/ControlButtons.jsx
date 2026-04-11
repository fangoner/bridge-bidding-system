import { Button, Badge, CircularProgress, Tooltip } from '@mui/material'
import HistoryIcon from '@mui/icons-material/History'
import UndoIcon from '@mui/icons-material/Undo'

function ControlButtons({
  size = 'large',
  showSettings,
  setShowSettings,
  loading,
  handleDeal,
  dealMode,
  hands,
  biddingStarted,
  isBiddingComplete,
  stopBidding,
  toggleStopBidding,
  isNewDeal,
  startBidding,
  biddingRecords,
  setHistoryDialogOpen,
  checkApiStatus,
  apiStatus,
  handleReloadJF,
  showUndo,
  canUndo,
  onUndo,
}) {
  const isLarge = size === 'large'
  const gap = isLarge ? 2 : 1
  const buttonSize = isLarge ? 'large' : 'small'
  const progressSize = isLarge ? 20 : 16
  
  return (
    <>
      <Button
        variant="outlined"
        size={buttonSize}
        onClick={() => setShowSettings(!showSettings)}
      >
        {showSettings ? '隐藏设置' : '显示设置'}
      </Button>

      <Button
        variant="contained"
        size={buttonSize}
        onClick={() => handleDeal(dealMode)}
        disabled={loading}
        startIcon={loading && <CircularProgress size={progressSize} />}
      >
        {loading ? '发牌中...' : '发牌'}
      </Button>

      <Button
        variant="outlined"
        size={buttonSize}
        onClick={startBidding}
        disabled={!hands || (biddingStarted && !isBiddingComplete() && !stopBidding)}
      >
        {isNewDeal ? '开始叫牌' : '重新叫牌'}
      </Button>
      
      {biddingStarted && !isBiddingComplete() && (
        <Button
          variant={stopBidding ? "contained" : "outlined"}
          color={stopBidding ? "success" : "warning"}
          size={buttonSize}
          onClick={toggleStopBidding}
        >
          {stopBidding ? (isLarge ? '继续叫牌' : '继续') : (isLarge ? '停止叫牌' : '暂停')}
        </Button>
      )}
      
      {showUndo && (
        <Tooltip title={canUndo ? "撤销上一步叫牌" : "AI正在思考..."}>
          <span>
            <Button
              variant="outlined"
              color="secondary"
              size={buttonSize}
              onClick={onUndo}
              disabled={!canUndo}
              startIcon={<UndoIcon />}
            >
              {isLarge ? '撤销' : ''}
            </Button>
          </span>
        </Tooltip>
      )}
      
      <Badge 
        badgeContent={biddingRecords.length} 
        color="primary"
        max={999}
        sx={{ '& .MuiBadge-badge': { fontSize: '0.7rem', height: '18px', minWidth: '18px' } }}
      >
        <Button
          variant="outlined"
          size={buttonSize}
          onClick={() => setHistoryDialogOpen(true)}
          startIcon={<HistoryIcon />}
        >
          {isLarge ? '历史记录' : '历史'}
        </Button>
      </Badge>
      
      <Button
        variant="outlined"
        size={buttonSize}
        onClick={checkApiStatus}
        sx={apiStatus?.error ? { borderColor: 'error.main', color: 'error.main', '&:hover': { borderColor: 'error.dark' } } : {}}
      >
        {isLarge ? '检查API状态' : 'API'}
      </Button>
      
      <Badge 
        badgeContent={apiStatus?.jf_segments_loaded || 0} 
        color="primary"
        max={999}
        sx={{ '& .MuiBadge-badge': { fontSize: '0.7rem', height: '18px', minWidth: '18px' } }}
      >
        <Button
          variant="outlined"
          size={buttonSize}
          onClick={handleReloadJF}
        >
          {isLarge ? '重新加载约定' : '约定'}
        </Button>
      </Badge>
    </>
  )
}

export default ControlButtons
