import { createTheme, alpha } from '@mui/material/styles'

const modernColors = {
  primary: {
    main: '#4f46e5',
    light: '#6366f1',
    dark: '#4338ca',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#f59e0b',
    light: '#fbbf24',
    dark: '#d97706',
    contrastText: '#ffffff',
  },
  suits: {
    spades: '#1e293b',
    hearts: '#dc2626',
    diamonds: '#ea580c',
    clubs: '#16a34a',
    notrump: '#475569',
  },
  error: {
    main: '#ef4444',
    light: '#f87171',
    dark: '#dc2626',
    contrastText: '#ffffff',
  },
  warning: {
    main: '#f59e0b',
    light: '#fbbf24',
    dark: '#d97706',
    contrastText: '#ffffff',
  },
  info: {
    main: '#3b82f6',
    light: '#60a5fa',
    dark: '#2563eb',
    contrastText: '#ffffff',
  },
  success: {
    main: '#10b981',
    light: '#34d399',
    dark: '#059669',
    contrastText: '#ffffff',
  },
  background: {
    default: '#f8fafc',
    paper: '#ffffff',
    table: '#0c4a3e',
  },
  text: {
    primary: '#0f172a',
    secondary: '#475569',
    disabled: '#94a3b8',
  },
  divider: '#e2e8f0',
  grey: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
  },
}

const darkColors = {
  primary: {
    main: '#818cf8',
    light: '#a5b4fc',
    dark: '#6366f1',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#fbbf24',
    light: '#fcd34d',
    dark: '#f59e0b',
    contrastText: '#1e293b',
  },
  background: {
    default: '#0f172a',
    paper: '#1e293b',
    table: '#032b24',
  },
  text: {
    primary: '#f1f5f9',
    secondary: '#94a3b8',
    disabled: '#64748b',
  },
  divider: '#334155',
  grey: {
    50: '#0f172a',
    100: '#1e293b',
    200: '#334155',
    300: '#475569',
    400: '#64748b',
    500: '#94a3b8',
    600: '#cbd5e1',
    700: '#e2e8f0',
    800: '#f1f5f9',
    900: '#f8fafc',
  },
}

function glass(isDark) {
  return {
    strong: {
      background: isDark
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(30, 41, 59, 0.6) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0.7) 100%)',
      backdropFilter: 'blur(24px) saturate(180%)',
      WebkitBackdropFilter: 'blur(24px) saturate(180%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.8)'}`,
      boxShadow: isDark
        ? '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)'
        : '0 8px 32px rgba(79, 70, 229, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.9)',
    },
    medium: {
      background: isDark
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.65) 0%, rgba(30, 41, 59, 0.5) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.8) 0%, rgba(255, 255, 255, 0.65) 100%)',
      backdropFilter: 'blur(20px) saturate(170%)',
      WebkitBackdropFilter: 'blur(20px) saturate(170%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.7)'}`,
      boxShadow: isDark
        ? '0 4px 16px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.04)'
        : '0 4px 20px rgba(79, 70, 229, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.9)',
    },
    weak: {
      background: isDark
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.5) 0%, rgba(30, 41, 59, 0.35) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0.55) 100%)',
      backdropFilter: 'blur(14px) saturate(140%)',
      WebkitBackdropFilter: 'blur(14px) saturate(140%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(255, 255, 255, 0.6)'}`,
      boxShadow: isDark
        ? '0 2px 8px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.03)'
        : '0 2px 12px rgba(79, 70, 229, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
    },
  }
}

function createAppTheme(mode = 'light') {
  const isDark = mode === 'dark'
  const baseColors = isDark ? { ...modernColors, ...darkColors } : { ...modernColors }
  if (isDark) {
    baseColors.suits = { ...modernColors.suits }
    baseColors.error = modernColors.error
    baseColors.warning = modernColors.warning
    baseColors.info = modernColors.info
    baseColors.success = modernColors.success
  }
  const colors = baseColors
  const glassPresets = glass(isDark)
  const textColor = colors.text.primary
  const textSecondary = colors.text.secondary

  const theme = createTheme({
    palette: {
      primary: colors.primary,
      secondary: colors.secondary,
      error: colors.error,
      warning: colors.warning,
      info: colors.info,
      success: colors.success,
      background: colors.background,
      text: colors.text,
      divider: colors.divider,
      grey: colors.grey,
      mode,
    },
    typography: {
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      h1: {
        fontSize: '2.5rem',
        fontWeight: 700,
        letterSpacing: '-0.025em',
        color: textColor,
        lineHeight: 1.2,
      },
      h2: {
        fontSize: '2rem',
        fontWeight: 700,
        letterSpacing: '-0.02em',
        color: textColor,
        lineHeight: 1.25,
      },
      h3: {
        fontSize: '1.5rem',
        fontWeight: 700,
        letterSpacing: '-0.015em',
        color: textColor,
        lineHeight: 1.3,
      },
      h4: {
        fontSize: '1.25rem',
        fontWeight: 600,
        color: textColor,
        letterSpacing: '-0.01em',
      },
      h5: {
        fontSize: '1.125rem',
        fontWeight: 600,
        color: textColor,
      },
      h6: {
        fontSize: '1rem',
        fontWeight: 600,
        color: textColor,
      },
      subtitle1: {
        fontSize: '1rem',
        fontWeight: 500,
        color: textSecondary,
      },
      subtitle2: {
        fontSize: '0.875rem',
        fontWeight: 500,
        color: textSecondary,
      },
      body1: {
        fontSize: '1rem',
        color: textColor,
        lineHeight: 1.6,
      },
      body2: {
        fontSize: '0.875rem',
        color: textSecondary,
        lineHeight: 1.6,
      },
      button: {
        fontWeight: 600,
        textTransform: 'none',
        letterSpacing: '0.01em',
      },
      caption: {
        fontSize: '0.75rem',
        color: textSecondary,
      },
    },
    shape: {
      borderRadius: 12,
    },
    shadows: [
      'none',
      isDark ? '0 1px 2px 0 rgba(0,0,0,0.3)' : '0 1px 3px 0 rgba(0,0,0,0.04), 0 1px 2px -1px rgba(0,0,0,0.04)',
      isDark ? '0 1px 3px 0 rgba(0,0,0,0.4)' : '0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.04)',
      isDark ? '0 4px 6px -1px rgba(0,0,0,0.4)' : '0 6px 12px -2px rgba(79,70,229,0.07), 0 3px 6px -3px rgba(0,0,0,0.05)',
      isDark ? '0 10px 15px -3px rgba(0,0,0,0.5)' : '0 10px 20px -3px rgba(79,70,229,0.08), 0 4px 8px -4px rgba(0,0,0,0.05)',
      isDark ? '0 20px 25px -5px rgba(0,0,0,0.5)' : '0 20px 30px -5px rgba(79,70,229,0.09), 0 8px 12px -6px rgba(0,0,0,0.05)',
      isDark ? '0 25px 50px -12px rgba(0,0,0,0.6)' : '0 25px 40px -12px rgba(79,70,229,0.1), 0 12px 20px -8px rgba(0,0,0,0.06)',
      ...Array(19).fill(isDark ? '0 25px 50px -12px rgba(0,0,0,0.6)' : '0 25px 40px -12px rgba(79,70,229,0.1), 0 12px 20px -8px rgba(0,0,0,0.06)'),
    ],
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            background: isDark
              ? 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 25%, #0f172a 50%, #1c1917 75%, #0c1a14 100%)'
              : 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 20%, #faf5ff 40%, #fff7ed 60%, #ecfdf5 80%, #f0f9ff 100%)',
            backgroundAttachment: 'fixed',
            minHeight: '100vh',
          },
        },
      },

      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 10,
            fontWeight: 600,
            padding: '8px 20px',
            transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
            textTransform: 'none',
          },
          contained: {
            boxShadow: isDark
              ? '0 4px 14px 0 rgba(129, 140, 248, 0.3)'
              : '0 4px 14px 0 rgba(79, 70, 229, 0.25)',
            '&:hover': {
              boxShadow: isDark
                ? '0 6px 20px 0 rgba(129, 140, 248, 0.4)'
                : '0 6px 20px 0 rgba(79, 70, 229, 0.35)',
              transform: 'translateY(-1px)',
            },
            '&:active': {
              transform: 'translateY(0)',
            },
          },
          containedPrimary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
            '&:hover': {
              background: `linear-gradient(135deg, ${colors.primary.dark} 0%, ${colors.primary.main} 100%)`,
            },
          },
          containedSecondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
            color: isDark ? '#1e293b' : '#ffffff',
            boxShadow: isDark
              ? '0 4px 14px 0 rgba(251, 191, 36, 0.3)'
              : '0 4px 14px 0 rgba(245, 158, 11, 0.25)',
            '&:hover': {
              background: `linear-gradient(135deg, ${colors.secondary.dark} 0%, ${colors.secondary.main} 100%)`,
              boxShadow: isDark
                ? '0 6px 20px 0 rgba(251, 191, 36, 0.4)'
                : '0 6px 20px 0 rgba(245, 158, 11, 0.35)',
            },
          },
          outlined: {
            borderWidth: 1.5,
            borderColor: colors.divider,
            '&:hover': {
              borderWidth: 1.5,
              borderColor: colors.primary.main,
              backgroundColor: alpha(colors.primary.main, 0.04),
            },
          },
          outlinedPrimary: {
            borderColor: alpha(colors.primary.main, 0.5),
            '&:hover': {
              backgroundColor: alpha(colors.primary.main, 0.06),
              borderColor: colors.primary.main,
            },
          },
          text: {
            '&:hover': {
              backgroundColor: alpha(colors.primary.main, 0.06),
            },
          },
        },
      },

      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            background: glassPresets.medium.background,
            backdropFilter: glassPresets.medium.backdropFilter,
            WebkitBackdropFilter: glassPresets.medium.WebkitBackdropFilter,
            border: glassPresets.medium.border,
            boxShadow: glassPresets.medium.boxShadow,
          },
          elevation0: {
            boxShadow: 'none',
          },
          elevation1: {
            boxShadow: isDark
              ? '0 1px 3px rgba(0,0,0,0.2), 0 1px 2px rgba(0,0,0,0.15)'
              : '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)',
          },
          elevation2: {
            boxShadow: isDark
              ? '0 4px 6px rgba(0,0,0,0.25), 0 2px 4px rgba(0,0,0,0.15)'
              : '0 4px 8px rgba(79,70,229,0.05), 0 2px 4px rgba(0,0,0,0.04)',
          },
          elevation3: {
            boxShadow: glassPresets.strong.boxShadow,
          },
        },
      },

      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            background: glassPresets.medium.background,
            backdropFilter: glassPresets.medium.backdropFilter,
            WebkitBackdropFilter: glassPresets.medium.WebkitBackdropFilter,
            border: glassPresets.medium.border,
            boxShadow: glassPresets.medium.boxShadow,
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              boxShadow: isDark
                ? '0 20px 30px -10px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)'
                : '0 20px 30px -10px rgba(79,70,229,0.1), inset 0 1px 0 rgba(255,255,255,0.9)',
              transform: 'translateY(-2px)',
              borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(79,70,229,0.12)',
            },
          },
        },
      },

      MuiCardContent: {
        styleOverrides: {
          root: {
            padding: 20,
            '&:last-child': {
              paddingBottom: 20,
            },
          },
        },
      },

      MuiAppBar: {
        styleOverrides: {
          root: {
            background: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            WebkitBackdropFilter: glassPresets.strong.WebkitBackdropFilter,
            boxShadow: isDark
              ? '0 1px 0 rgba(255,255,255,0.05), 0 4px 20px rgba(0,0,0,0.2)'
              : '0 1px 0 rgba(0,0,0,0.04), 0 4px 20px rgba(79,70,229,0.05)',
            borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.8)'}`,
          },
          colorPrimary: {
            backgroundColor: 'transparent',
            color: textColor,
          },
        },
      },

      MuiToolbar: {
        styleOverrides: {
          root: {
            minHeight: '56px !important',
            '@media (min-width: 600px)': {
              minHeight: '60px !important',
            },
          },
        },
      },

      MuiAlert: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            fontWeight: 500,
          },
          standardSuccess: {
            backgroundColor: isDark ? alpha(colors.success.main, 0.12) : alpha(colors.success.main, 0.08),
            color: isDark ? colors.success.light : colors.success.dark,
            border: `1px solid ${alpha(colors.success.main, 0.2)}`,
          },
          standardError: {
            backgroundColor: isDark ? alpha(colors.error.main, 0.12) : alpha(colors.error.main, 0.08),
            color: isDark ? colors.error.light : colors.error.dark,
            border: `1px solid ${alpha(colors.error.main, 0.2)}`,
          },
          standardWarning: {
            backgroundColor: isDark ? alpha(colors.warning.main, 0.12) : alpha(colors.warning.main, 0.08),
            color: isDark ? colors.warning.light : colors.warning.dark,
            border: `1px solid ${alpha(colors.warning.main, 0.2)}`,
          },
          standardInfo: {
            backgroundColor: isDark ? alpha(colors.info.main, 0.12) : alpha(colors.info.main, 0.08),
            color: isDark ? colors.info.light : colors.info.dark,
            border: `1px solid ${alpha(colors.info.main, 0.2)}`,
          },
        },
      },

      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            fontWeight: 500,
            height: 28,
          },
          colorPrimary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
          colorSecondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
            color: isDark ? '#1e293b' : '#ffffff',
          },
          outlined: {
            borderColor: alpha(colors.primary.main, 0.3),
          },
        },
      },

      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 10,
              transition: 'all 0.2s ease',
              backgroundColor: isDark ? alpha('#000000', 0.1) : alpha('#ffffff', 0.5),
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: alpha(colors.primary.main, 0.4),
              },
              '&.Mui-focused': {
                backgroundColor: isDark ? alpha('#000000', 0.15) : alpha('#ffffff', 0.8),
              },
            },
          },
        },
      },

      MuiSelect: {
        styleOverrides: {
          root: {
            borderRadius: 10,
          },
        },
      },

      MuiTab: {
        styleOverrides: {
          root: {
            fontWeight: 600,
            textTransform: 'none',
            borderRadius: '10px 10px 0 0',
            minHeight: 44,
            padding: '6px 16px',
            transition: 'all 0.2s ease',
            '&.Mui-selected': {
              background: isDark
                ? alpha(colors.primary.main, 0.15)
                : alpha(colors.primary.main, 0.08),
              color: colors.primary.main,
            },
            '&:hover:not(.Mui-selected)': {
              backgroundColor: isDark ? alpha('#ffffff', 0.04) : alpha('#000000', 0.03),
            },
          },
        },
      },
      MuiTabs: {
        styleOverrides: {
          indicator: {
            height: 3,
            borderRadius: '3px 3px 0 0',
            background: `linear-gradient(90deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
        },
      },

      MuiSwitch: {
        styleOverrides: {
          root: {
            width: 48,
            height: 28,
            padding: 0,
          },
          switchBase: {
            padding: 4,
            '&.Mui-checked': {
              transform: 'translateX(20px)',
              color: '#ffffff',
              '& + .MuiSwitch-track': {
                background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
                opacity: 1,
              },
            },
          },
          thumb: {
            width: 20,
            height: 20,
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
          },
          track: {
            borderRadius: 14,
            backgroundColor: isDark ? colors.grey[600] : colors.grey[300],
            opacity: 1,
          },
        },
      },

      MuiCheckbox: {
        styleOverrides: {
          root: {
            '&.Mui-checked': {
              color: colors.primary.main,
            },
          },
        },
      },
      MuiRadio: {
        styleOverrides: {
          root: {
            '&.Mui-checked': {
              color: colors.primary.main,
            },
          },
        },
      },

      MuiFab: {
        styleOverrides: {
          root: {
            boxShadow: isDark
              ? '0 4px 14px 0 rgba(129, 140, 248, 0.3)'
              : '0 4px 14px 0 rgba(79, 70, 229, 0.3)',
            '&:hover': {
              boxShadow: isDark
                ? '0 6px 20px 0 rgba(129, 140, 248, 0.4)'
                : '0 6px 20px 0 rgba(79, 70, 229, 0.4)',
            },
          },
          primary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
          secondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
            boxShadow: isDark
              ? '0 4px 14px 0 rgba(251, 191, 36, 0.3)'
              : '0 4px 14px 0 rgba(245, 158, 11, 0.3)',
          },
        },
      },

      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            borderRadius: 8,
            backgroundColor: isDark ? alpha('#1e293b', 0.95) : alpha('#1e293b', 0.92),
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            color: '#f8fafc',
            fontSize: '0.8125rem',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            padding: '6px 12px',
          },
          arrow: {
            color: isDark ? alpha('#1e293b', 0.95) : alpha('#1e293b', 0.92),
          },
        },
      },

      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: 16,
            background: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            WebkitBackdropFilter: glassPresets.strong.WebkitBackdropFilter,
            border: glassPresets.strong.border,
            boxShadow: glassPresets.strong.boxShadow,
          },
        },
      },
      MuiBackdrop: {
        styleOverrides: {
          root: {
            backdropFilter: 'blur(6px)',
            WebkitBackdropFilter: 'blur(6px)',
            backgroundColor: isDark ? 'rgba(0,0,0,0.6)' : 'rgba(15,23,42,0.2)',
          },
        },
      },

      MuiDialogTitle: {
        styleOverrides: {
          root: {
            fontSize: '1.25rem',
            fontWeight: 700,
            padding: '20px 24px 12px',
          },
        },
      },
      MuiDialogContent: {
        styleOverrides: {
          root: {
            padding: '8px 24px 20px',
          },
        },
      },
      MuiDialogActions: {
        styleOverrides: {
          root: {
            padding: '12px 24px 20px',
          },
        },
      },

      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: 6,
            height: 6,
            backgroundColor: isDark ? alpha('#ffffff', 0.08) : alpha('#000000', 0.06),
          },
          bar: {
            borderRadius: 6,
            background: `linear-gradient(90deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
        },
      },
      MuiCircularProgress: {
        styleOverrides: {
          root: {
            color: colors.primary.main,
          },
        },
      },

      MuiAvatar: {
        styleOverrides: {
          root: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
            fontWeight: 600,
          },
        },
      },

      MuiBadge: {
        styleOverrides: {
          badge: {
            fontWeight: 600,
          },
        },
      },

      MuiDivider: {
        styleOverrides: {
          root: {
            borderColor: isDark ? alpha('#ffffff', 0.08) : colors.divider,
          },
        },
      },

      MuiInputLabel: {
        styleOverrides: {
          root: {
            '&.Mui-focused': {
              color: colors.primary.main,
            },
          },
        },
      },

      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: isDark ? alpha('#ffffff', 0.15) : colors.divider,
              transition: 'border-color 0.2s ease',
            },
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: isDark ? alpha('#ffffff', 0.25) : colors.grey[400],
            },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
              borderColor: colors.primary.main,
              borderWidth: 2,
            },
          },
        },
      },

      MuiTable: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            overflow: 'hidden',
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderBottom: `1px solid ${isDark ? alpha('#ffffff', 0.06) : colors.divider}`,
            padding: '12px 16px',
          },
          head: {
            fontWeight: 600,
            backgroundColor: isDark ? alpha('#ffffff', 0.02) : alpha('#000000', 0.01),
            color: textSecondary,
          },
        },
      },

      MuiIconButton: {
        styleOverrides: {
          root: {
            borderRadius: 10,
            transition: 'all 0.2s ease',
            '&:hover': {
              backgroundColor: isDark ? alpha('#ffffff', 0.08) : alpha(colors.primary.main, 0.06),
            },
          },
        },
      },

      MuiMenu: {
        styleOverrides: {
          paper: {
            borderRadius: 12,
            marginTop: 4,
            background: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            WebkitBackdropFilter: glassPresets.strong.WebkitBackdropFilter,
            border: glassPresets.strong.border,
            boxShadow: isDark
              ? '0 12px 32px rgba(0,0,0,0.4)'
              : '0 12px 32px rgba(79,70,229,0.12)',
          },
        },
      },
      MuiMenuItem: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            margin: '2px 6px',
            minHeight: 40,
            '&:hover': {
              backgroundColor: isDark ? alpha('#ffffff', 0.06) : alpha(colors.primary.main, 0.06),
            },
            '&.Mui-selected': {
              backgroundColor: isDark ? alpha(colors.primary.main, 0.15) : alpha(colors.primary.main, 0.1),
              '&:hover': {
                backgroundColor: isDark ? alpha(colors.primary.main, 0.2) : alpha(colors.primary.main, 0.14),
              },
            },
          },
        },
      },
    },
  })

  theme.suits = colors.suits
  theme.glass = glassPresets

  return theme
}

export { createAppTheme }
export default createAppTheme('light')
