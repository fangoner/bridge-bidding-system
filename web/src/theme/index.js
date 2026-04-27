import { createTheme, alpha } from '@mui/material/styles'

const modernColors = {
  primary: {
    main: '#6366f1',
    light: '#818cf8',
    dark: '#4f46e5',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#ec4899',
    light: '#f472b6',
    dark: '#db2777',
    contrastText: '#ffffff',
  },
  suits: {
    spades: '#1e293b',
    hearts: '#ef4444',
    diamonds: '#f97316',
    clubs: '#22c55e',
    notrump: '#8b5cf6',
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
    table: '#0f172a',
  },
  text: {
    primary: '#1e293b',
    secondary: '#64748b',
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
  background: {
    default: '#0f172a',
    paper: '#1e293b',
    table: '#020617',
  },
  text: {
    primary: '#e2e8f0',
    secondary: '#94a3b8',
    disabled: '#64748b',
  },
  divider: '#334155',
  grey: {
    50: '#1e293b',
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

function createAppTheme(mode = 'light') {
  const isDark = mode === 'dark'
  const colors = isDark ? { ...modernColors, ...darkColors } : modernColors
  const textColor = colors.text.primary
  const textSecondary = colors.text.secondary

  return createTheme({
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
      fontFamily: '"Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      h1: {
        fontSize: '2.5rem',
        fontWeight: 700,
        letterSpacing: '-0.02em',
        color: textColor,
      },
      h2: {
        fontSize: '2rem',
        fontWeight: 700,
        letterSpacing: '-0.01em',
        color: textColor,
      },
      h3: {
        fontSize: '1.5rem',
        fontWeight: 600,
        letterSpacing: '-0.01em',
        color: textColor,
      },
      h4: {
        fontSize: '1.25rem',
        fontWeight: 600,
        color: textColor,
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
      },
      body2: {
        fontSize: '0.875rem',
        color: textSecondary,
      },
      button: {
        fontWeight: 600,
        textTransform: 'none',
      },
    },
    shape: {
      borderRadius: 12,
    },
    shadows: [
      'none',
      '0 1px 2px 0 rgb(0 0 0 / 0.05)',
      '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
      '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
      '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
      '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
      '0 25px 50px -12px rgb(0 0 0 / 0.25)',
      ...Array(18).fill('0 25px 50px -12px rgb(0 0 0 / 0.25)'),
    ],
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            background: isDark
              ? 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #1e293b 100%)'
              : 'linear-gradient(135deg, #f8fafc 0%, #e0e7ff 50%, #fce7f3 100%)',
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
            padding: '10px 20px',
            transition: 'all 0.2s ease',
            '&:hover': {
              transform: 'translateY(-1px)',
            },
          },
          contained: {
            boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.25)',
            '&:hover': {
              boxShadow: '0 6px 20px 0 rgba(99, 102, 241, 0.35)',
            },
          },
          containedPrimary: {
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
            },
          },
          containedSecondary: {
            background: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
            boxShadow: '0 4px 14px 0 rgba(236, 72, 153, 0.25)',
            '&:hover': {
              background: 'linear-gradient(135deg, #db2777 0%, #ec4899 100%)',
              boxShadow: '0 6px 20px 0 rgba(236, 72, 153, 0.35)',
            },
          },
          outlined: {
            borderWidth: 2,
            '&:hover': {
              borderWidth: 2,
            },
          },
          outlinedPrimary: {
            borderColor: colors.primary.main,
            '&:hover': {
              backgroundColor: alpha(colors.primary.main, 0.08),
              borderColor: colors.primary.dark,
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            backgroundImage: 'none',
            backgroundColor: isDark
              ? alpha('#1e293b', 0.95)
              : alpha('#ffffff', 0.9),
            backdropFilter: 'blur(10px)',
          },
          elevation1: {
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)',
          },
          elevation2: {
            boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.05), 0 4px 6px -4px rgb(0 0 0 / 0.05)',
          },
          elevation3: {
            boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.05), 0 8px 10px -6px rgb(0 0 0 / 0.05)',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            border: `1px solid ${alpha(colors.primary.main, isDark ? 0.15 : 0.1)}`,
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
            transition: 'all 0.3s ease',
            '&:hover': {
              boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)',
              transform: 'translateY(-2px)',
            },
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
            boxShadow: '0 4px 20px 0 rgba(99, 102, 241, 0.3)',
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
            backgroundColor: alpha(colors.success.main, isDark ? 0.15 : 0.1),
            color: isDark ? colors.success.light : colors.success.dark,
            border: `1px solid ${alpha(colors.success.main, 0.2)}`,
          },
          standardError: {
            backgroundColor: alpha(colors.error.main, isDark ? 0.15 : 0.1),
            color: isDark ? colors.error.light : colors.error.dark,
            border: `1px solid ${alpha(colors.error.main, 0.2)}`,
          },
          standardWarning: {
            backgroundColor: alpha(colors.warning.main, isDark ? 0.15 : 0.1),
            color: isDark ? colors.warning.light : colors.warning.dark,
            border: `1px solid ${alpha(colors.warning.main, 0.2)}`,
          },
          standardInfo: {
            backgroundColor: alpha(colors.info.main, isDark ? 0.15 : 0.1),
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
          },
          colorPrimary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
          colorSecondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 10,
              transition: 'all 0.2s ease',
              '&:hover': {
                boxShadow: `0 0 0 2px ${alpha(colors.primary.main, 0.1)}`,
              },
              '&.Mui-focused': {
                boxShadow: `0 0 0 3px ${alpha(colors.primary.main, 0.15)}`,
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
            borderRadius: '8px 8px 0 0',
            '&.Mui-selected': {
              background: alpha(colors.primary.main, 0.1),
            },
          },
        },
      },
      MuiTabs: {
        styleOverrides: {
          indicator: {
            height: 3,
            borderRadius: '3px 3px 0 0',
            background: `linear-gradient(90deg, ${colors.primary.main} 0%, ${colors.secondary.main} 100%)`,
          },
        },
      },
      MuiSwitch: {
        styleOverrides: {
          root: {
            width: 52,
            height: 30,
            padding: 0,
          },
          switchBase: {
            padding: 3,
            '&.Mui-checked': {
              transform: 'translateX(22px)',
              '& + .MuiSwitch-track': {
                backgroundColor: colors.primary.main,
                opacity: 1,
              },
            },
          },
          thumb: {
            width: 24,
            height: 24,
            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
          },
          track: {
            borderRadius: 15,
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
            boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.3)',
          },
          primary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
          secondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
            boxShadow: '0 4px 14px 0 rgba(236, 72, 153, 0.3)',
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            borderRadius: 8,
            backgroundColor: isDark ? colors.grey[700] : colors.grey[800],
            fontSize: '0.8125rem',
          },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: 20,
            boxShadow: '0 25px 50px -12px rgb(0 0 0 / 0.25)',
          },
        },
      },
      MuiDialogTitle: {
        styleOverrides: {
          root: {
            fontSize: '1.25rem',
            fontWeight: 700,
          },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: 4,
            height: 8,
          },
          bar: {
            background: `linear-gradient(90deg, ${colors.primary.main} 0%, ${colors.secondary.main} 100%)`,
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
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.secondary.main} 100%)`,
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
            borderColor: isDark ? alpha('#ffffff', 0.12) : undefined,
          },
        },
      },
      MuiInputLabel: {
        styleOverrides: {
          root: isDark ? {
            '&.Mui-focused': {
              color: colors.primary.light,
            },
          } : undefined,
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: isDark ? {
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: alpha('#ffffff', 0.23),
            },
          } : undefined,
        },
      },
    },
  })
}

export { createAppTheme }
export default createAppTheme('light')
