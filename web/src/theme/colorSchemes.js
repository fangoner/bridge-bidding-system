export const colorSchemes = {
  classicGreen: {
    name: '森林绿茵',
    nameEn: 'classicGreen',
    table: {
      // 径向发光：中心亮、边缘暗，模拟桌面灯光
      background: 'radial-gradient(ellipse at center, #3d7a58 0%, #25563b 40%, #1a3d28 100%)',
      border: '3px solid rgba(255, 255, 255, 0.12)',
      // 中央区域：强毛玻璃
      centerBg: 'rgba(255, 255, 255, 0.45)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 255, 255, 0.25)',
    },
    button: {
      primary: '#4ade80',
      primaryHover: '#22c55e',
      text: 'white',
    },
    accent: '#4ade80',
  },
  midnightIndigo: {
    name: '深靛夜幕',
    nameEn: 'midnightIndigo',
    table: {
      background: 'radial-gradient(ellipse at center, #312e81 0%, #1e1b4b 40%, #0f0d2e 100%)',
      border: '3px solid rgba(255, 255, 255, 0.12)',
      centerBg: 'rgba(255, 255, 255, 0.08)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 255, 255, 0.12)',
    },
    button: {
      primary: '#818cf8',
      primaryHover: '#6366f1',
      text: 'white',
    },
    accent: '#a78bfa',
  },
  deepBlue: {
    name: '深蓝典雅',
    nameEn: 'deepBlue',
    table: {
      background: 'radial-gradient(ellipse at center, #1a3a7a 0%, #0d1f5c 40%, #081038 100%)',
      border: '3px solid rgba(255, 255, 255, 0.12)',
      centerBg: 'rgba(255, 255, 255, 0.08)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 255, 255, 0.12)',
    },
    button: {
      primary: '#64b5f6',
      primaryHover: '#42a5f5',
      text: 'white',
    },
    accent: '#64b5f6',
  },
  vintageBrown: {
    name: '复古棕木',
    nameEn: 'vintageBrown',
    table: {
      background: 'radial-gradient(ellipse at center, #6d4c3d 0%, #4a3028 40%, #2e1d18 100%)',
      border: '3px solid rgba(255, 215, 0, 0.12)',
      centerBg: 'rgba(255, 248, 225, 0.08)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 215, 0, 0.15)',
    },
    button: {
      primary: '#ffb74d',
      primaryHover: '#ffa726',
      text: 'white',
    },
    accent: '#ffb74d',
  },
  minimalGray: {
    name: '简约灰调',
    nameEn: 'minimalGray',
    table: {
      background: 'radial-gradient(ellipse at center, #4a555e 0%, #2d363d 40%, #1a2025 100%)',
      border: '3px solid rgba(255, 255, 255, 0.1)',
      centerBg: 'rgba(255, 255, 255, 0.06)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 255, 255, 0.08)',
    },
    button: {
      primary: '#ff5722',
      primaryHover: '#e64a19',
      text: 'white',
    },
    accent: '#78909c',
  },
  royalPurple: {
    name: '皇家紫金',
    nameEn: 'royalPurple',
    table: {
      background: 'radial-gradient(ellipse at center, #5b1a8c 0%, #351560 40%, #1d0a38 100%)',
      border: '3px solid rgba(255, 215, 0, 0.15)',
      centerBg: 'rgba(255, 255, 255, 0.08)',
      centerBackdrop: 'blur(16px) saturate(160%)',
      centerBorder: '1px solid rgba(255, 215, 0, 0.15)',
    },
    button: {
      primary: '#ffc107',
      primaryHover: '#ffb300',
      text: '#1a1a1a',
    },
    accent: '#ce93d8',
  },
};

export const defaultScheme = 'classicGreen';
