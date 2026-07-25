import { Button, Badge, CircularProgress, Tooltip, IconButton, FormControl, InputLabel, Select, MenuItem } from '@mui/material'
import HistoryIcon from '@mui/icons-material/History'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'

function ControlButtons({
  size = 'large',
    showSettings,
  setShowSettings,
        biddingRecords,
  setHistoryDialogOpen,
  checkApiStatus,
  apiStatus,
  handleReloadJF,
  darkMode,
  onToggleDarkMode,
  aiThinking,
  vulnerability,
  setVulnerability,
}) {
  const isLarge = size === 'large'
  const buttonSize = isLarge ? 'large' : 'small'

  return (
    <>
      <Button
        variant="outlined"
        size={buttonSize}
        onClick={() => setShowSettings(!showSettings)}
      >
        {showSettings ? '隐藏设置' : '设置'}
      </Button>

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
          disabled={aiThinking}
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
      
      <Tooltip title={darkMode ? '切换明亮模式' : '切换暗色模式'}>
        <IconButton onClick={onToggleDarkMode} size={buttonSize} sx={{ ml: 1 }}>
          {darkMode ? <LightModeIcon /> : <DarkModeIcon />}
        </IconButton>
      </Tooltip>
    </>
  )
}

export default ControlButtons
