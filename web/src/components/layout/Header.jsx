import React from 'react';
import { Box, Button, Typography, useMediaQuery, useTheme } from '@mui/material';
import ControlButtons from '../ControlButtons';

/**
 * 统一的页面标题栏，桌面/移动端自适应。
 *
 * Props 透传给 ControlButtons（mode, loading, darkMode, aiThinking 等），
 * 加上 onBack 回调用于退出当前模式。
 */
export default function Header({ onBack, mode, ...controlProps }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  return (
    <Box sx={{
      mb: 2, display: 'flex', flexWrap: 'wrap',
      justifyContent: 'center', gap: isMobile ? 1 : 2, alignItems: 'center',
    }}>
      <Button
        variant="text"
        size="small"
        onClick={onBack}
        sx={{ fontSize: isMobile ? '0.7rem' : '0.75rem', textTransform: 'none' }}
      >
        ← 返回
      </Button>

      <Typography
        variant="h4"
        component="h1"
        sx={{ fontSize: isMobile ? '1.25rem' : '1.75rem', whiteSpace: 'nowrap' }}
      >
        桥牌练习系统
        {!isMobile && (
          <Typography component="span" sx={{ fontSize: '1rem', color: 'text.secondary', ml: 1 }}>
            {mode === 'practice' ? '— 发牌练习' : '— 模拟实战'}
          </Typography>
        )}
      </Typography>

      <ControlButtons
        size={isMobile ? 'medium' : 'large'}
        mode={mode}
        {...controlProps}
      />
    </Box>
  );
}
