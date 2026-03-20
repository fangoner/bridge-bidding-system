// Design tokens for bridge bidding system
// CSS custom properties and JavaScript constants

// Colors
export const colors = {
  // Primary
  primary: {
    main: '#2e7d32',
    light: '#4caf50',
    dark: '#1b5e20',
    contrastText: '#ffffff',
  },
  // Secondary
  secondary: {
    main: '#1976d2',
    light: '#42a5f5',
    dark: '#1565c0',
    contrastText: '#ffffff',
  },
  // Suits
  suits: {
    spades: '#000000',
    hearts: '#d32f2f',
    diamonds: '#ff9800',
    clubs: '#388e3c',
    notrump: '#5d4037',
  },
  // Semantic colors
  error: '#d32f2f',
  warning: '#ed6c02',
  info: '#0288d1',
  success: '#2e7d32',
  // Backgrounds
  background: {
    default: '#f5f5f5',
    paper: '#ffffff',
    table: '#1b5e20',
  },
  // Text
  text: {
    primary: 'rgba(0, 0, 0, 0.87)',
    secondary: 'rgba(0, 0, 0, 0.6)',
    disabled: 'rgba(0, 0, 0, 0.38)',
  },
  // Borders & dividers
  border: {
    light: 'rgba(0, 0, 0, 0.12)',
    medium: 'rgba(0, 0, 0, 0.24)',
    heavy: 'rgba(0, 0, 0, 0.36)',
  },
  // States
  state: {
    hover: 'rgba(0, 0, 0, 0.04)',
    selected: 'rgba(0, 0, 0, 0.08)',
    disabled: 'rgba(0, 0, 0, 0.26)',
    focus: '#1976d2',
  },
};

// Spacing (8px base unit)
export const spacing = {
  unit: 8,
  xs: '4px',   // 0.5 * unit
  sm: '8px',   // 1 * unit
  md: '16px',  // 2 * unit
  lg: '24px',  // 3 * unit
  xl: '32px',  // 4 * unit
  xxl: '48px', // 6 * unit
  xxxl: '64px', // 8 * unit
};

// Typography
export const typography = {
  fontFamily: {
    system: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    monospace: '"Courier New", Courier, monospace',
    serif: 'Georgia, "Times New Roman", Times, serif',
  },
  fontSize: {
    xs: '0.75rem',   // 12px
    sm: '0.875rem',  // 14px
    md: '1rem',      // 16px
    lg: '1.125rem',  // 18px
    xl: '1.25rem',   // 20px
    xxl: '1.5rem',   // 24px
    xxxl: '2rem',    // 32px
  },
  fontWeight: {
    light: 300,
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
};

// Breakpoints (Material Design standard)
export const breakpoints = {
  xs: 0,
  sm: 600,
  md: 960,
  lg: 1280,
  xl: 1920,
};

// Shadows (Material Design elevation)
export const shadows = {
  0: 'none',
  1: '0px 2px 1px -1px rgba(0,0,0,0.2),0px 1px 1px 0px rgba(0,0,0,0.14),0px 1px 3px 0px rgba(0,0,0,0.12)',
  2: '0px 3px 1px -2px rgba(0,0,0,0.2),0px 2px 2px 0px rgba(0,0,0,0.14),0px 1px 5px 0px rgba(0,0,0,0.12)',
  3: '0px 3px 3px -2px rgba(0,0,0,0.2),0px 3px 4px 0px rgba(0,0,0,0.14),0px 1px 8px 0px rgba(0,0,0,0.12)',
  4: '0px 2px 4px -1px rgba(0,0,0,0.2),0px 4px 5px 0px rgba(0,0,0,0.14),0px 1px 10px 0px rgba(0,0,0,0.12)',
  6: '0px 3px 5px -1px rgba(0,0,0,0.2),0px 6px 10px 0px rgba(0,0,0,0.14),0px 1px 18px 0px rgba(0,0,0,0.12)',
  8: '0px 5px 5px -3px rgba(0,0,0,0.2),0px 8px 10px 1px rgba(0,0,0,0.14),0px 3px 14px 2px rgba(0,0,0,0.12)',
  12: '0px 7px 8px -4px rgba(0,0,0,0.2),0px 12px 17px 2px rgba(0,0,0,0.14),0px 5px 22px 4px rgba(0,0,0,0.12)',
  16: '0px 8px 10px -5px rgba(0,0,0,0.2),0px 16px 24px 2px rgba(0,0,0,0.14),0px 6px 30px 5px rgba(0,0,0,0.12)',
  24: '0px 11px 15px -7px rgba(0,0,0,0.2),0px 24px 38px 3px rgba(0,0,0,0.14),0px 9px 46px 8px rgba(0,0,0,0.12)',
};

// Border radius
export const borderRadius = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  round: '50%',
};

// Z-index layers
export const zIndex = {
  appBar: 1100,
  drawer: 1200,
  modal: 1300,
  snackbar: 1400,
  tooltip: 1500,
};

// Animation durations
export const animation = {
  fast: '150ms',
  normal: '250ms',
  slow: '350ms',
};

// Responsive utility functions
export const responsive = {
  // Media query helpers
  up: (breakpoint) => `@media (min-width: ${breakpoints[breakpoint]}px)`,
  down: (breakpoint) => `@media (max-width: ${breakpoints[breakpoint] - 0.05}px)`,
  between: (start, end) => `@media (min-width: ${breakpoints[start]}px) and (max-width: ${breakpoints[end] - 0.05}px)`,
  // Spacing helpers
  spacing: (multiplier) => `${spacing.unit * multiplier}px`,
  // Typography helpers
  fontSize: (size) => typography.fontSize[size] || size,
};

// CSS custom properties for use in global styles
export const cssVariables = {
  '--color-primary-main': colors.primary.main,
  '--color-primary-light': colors.primary.light,
  '--color-primary-dark': colors.primary.dark,
  '--color-secondary-main': colors.secondary.main,
  '--color-secondary-light': colors.secondary.light,
  '--color-secondary-dark': colors.secondary.dark,
  '--color-suit-spades': colors.suits.spades,
  '--color-suit-hearts': colors.suits.hearts,
  '--color-suit-diamonds': colors.suits.diamonds,
  '--color-suit-clubs': colors.suits.clubs,
  '--color-suit-notrump': colors.suits.notrump,
  '--color-error': colors.error,
  '--color-warning': colors.warning,
  '--color-info': colors.info,
  '--color-success': colors.success,
  '--color-background-default': colors.background.default,
  '--color-background-paper': colors.background.paper,
  '--color-background-table': colors.background.table,
  '--color-text-primary': colors.text.primary,
  '--color-text-secondary': colors.text.secondary,
  '--color-text-disabled': colors.text.disabled,
  '--color-border-light': colors.border.light,
  '--color-border-medium': colors.border.medium,
  '--color-border-heavy': colors.border.heavy,
  '--spacing-unit': `${spacing.unit}px`,
  '--spacing-xs': spacing.xs,
  '--spacing-sm': spacing.sm,
  '--spacing-md': spacing.md,
  '--spacing-lg': spacing.lg,
  '--spacing-xl': spacing.xl,
  '--spacing-xxl': spacing.xxl,
  '--spacing-xxxl': spacing.xxxl,
  '--font-family-system': typography.fontFamily.system,
  '--font-family-monospace': typography.fontFamily.monospace,
  '--font-family-serif': typography.fontFamily.serif,
  '--font-size-xs': typography.fontSize.xs,
  '--font-size-sm': typography.fontSize.sm,
  '--font-size-md': typography.fontSize.md,
  '--font-size-lg': typography.fontSize.lg,
  '--font-size-xl': typography.fontSize.xl,
  '--font-size-xxl': typography.fontSize.xxl,
  '--font-size-xxxl': typography.fontSize.xxxl,
  '--font-weight-light': typography.fontWeight.light,
  '--font-weight-regular': typography.fontWeight.regular,
  '--font-weight-medium': typography.fontWeight.medium,
  '--font-weight-semibold': typography.fontWeight.semibold,
  '--font-weight-bold': typography.fontWeight.bold,
  '--line-height-tight': typography.lineHeight.tight,
  '--line-height-normal': typography.lineHeight.normal,
  '--line-height-relaxed': typography.lineHeight.relaxed,
  '--border-radius-xs': borderRadius.xs,
  '--border-radius-sm': borderRadius.sm,
  '--border-radius-md': borderRadius.md,
  '--border-radius-lg': borderRadius.lg,
  '--border-radius-xl': borderRadius.xl,
  '--border-radius-round': borderRadius.round,
  '--shadow-0': shadows[0],
  '--shadow-1': shadows[1],
  '--shadow-2': shadows[2],
  '--shadow-3': shadows[3],
  '--shadow-4': shadows[4],
  '--shadow-6': shadows[6],
  '--shadow-8': shadows[8],
  '--shadow-12': shadows[12],
  '--shadow-16': shadows[16],
  '--shadow-24': shadows[24],
  '--animation-fast': animation.fast,
  '--animation-normal': animation.normal,
  '--animation-slow': animation.slow,
};

export default {
  colors,
  spacing,
  typography,
  breakpoints,
  shadows,
  borderRadius,
  zIndex,
  animation,
  responsive,
  cssVariables,
};