import { Component } from 'react'
import { Box, Typography, Button, Paper } from '@mui/material'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })
    // 记录错误详情到控制台
    console.error('[ErrorBoundary] 捕获到渲染错误:', error)
    console.error('[ErrorBoundary] 组件堆栈:', errorInfo?.componentStack)
  }

  handleReload = () => {
    // 清除草稿后刷新页面
    try {
      localStorage.removeItem('bridge_bidding_draft')
    } catch (e) {
      // ignore
    }
    window.location.reload()
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  render() {
    if (this.state.hasError) {
      // 允许自定义 fallback
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          errorInfo: this.state.errorInfo,
          onReload: this.handleReload,
          onReset: this.handleReset,
        })
      }

      return (
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            p: 3,
            bgcolor: '#f5f5f5',
          }}
        >
          <Paper
            elevation={3}
            sx={{
              p: 4,
              maxWidth: 600,
              width: '100%',
              textAlign: 'center',
            }}
          >
            <ErrorOutlineIcon color="error" sx={{ fontSize: 64, mb: 2 }} />
            <Typography variant="h5" gutterBottom color="error">
              页面发生错误
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
              应用遇到了一个意外错误，请尝试刷新页面恢复。
              如果问题持续出现，请清除浏览器缓存后重试。
            </Typography>
            <Box
              component="details"
              sx={{
                mb: 3,
                textAlign: 'left',
                bgcolor: '#fff3f3',
                p: 2,
                borderRadius: 1,
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              <Typography
                component="summary"
                variant="body2"
                sx={{ cursor: 'pointer', fontWeight: 'bold', color: '#d32f2f' }}
              >
                错误详情（点击展开）
              </Typography>
              <Typography variant="body2" sx={{ mt: 1, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                {this.state.error?.toString() || '未知错误'}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
              <Button variant="outlined" onClick={this.handleReset}>
                尝试恢复
              </Button>
              <Button variant="contained" color="primary" onClick={this.handleReload}>
                刷新页面
              </Button>
            </Box>
          </Paper>
        </Box>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
