import { createTheme, alpha } from '@mui/material/styles'

// ── "Midnight Sapphire" palette ──────────────────────────────────────────────
const modernColors = {
  primary: {
    main: '#5b5fe3',      // warmer sapphire (was #6366f1)
    light: '#818cf8',
    dark: '#4c51bf',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#d9469a',      // softer rose (was #ec4899)
    light: '#f472b6',
    dark: '#be2d7d',
    contrastText: '#ffffff',
  },
  suits: {
    spades: '#1e293b',
    hearts: '#ef4444',
    diamonds: '#f59e0b',  // amber for better distinction from hearts
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
    default: '#e2e7ed',   // cool light gray
    paper: '#f2f4f7',     // slightly off-white
    table: '#0f172a',
  },
  text: {
    primary: '#1e293b',
    secondary: '#64748b',
    disabled: '#94a3b8',
  },
  divider: '#ccd5e0',
  grey: {
    50: '#f2f4f7',
    100: '#e8ecf1',
    200: '#dce2eb',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
  },
}

// ── Dark-mode overrides ──────────────────────────────────────────────────────
const darkColors = {
  background: {
    default: '#0b1120',   // deeper night (was #0f172a)
    paper: '#111827',     // darker card surface (was #1e293b)
    table: '#020617',
  },
  text: {
    primary: '#e2e8f0',
    secondary: '#94a3b8',
    disabled: '#64748b',
  },
  divider: '#1e293b',
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

// ── Glass surface presets ────────────────────────────────────────────────────
function glass(isDark) {
  return {
    strong: {
      background: isDark
        ? 'linear-gradient(135deg, rgba(17, 24, 39, 0.65) 0%, rgba(17, 24, 39, 0.55) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0.45) 100%)',
      backdropFilter: 'blur(24px) saturate(180%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)'}`,
      boxShadow: isDark
        ? '0 8px 32px rgba(0, 0, 0, 0.4)'
        : '0 8px 32px rgba(0, 0, 0, 0.06)',
    },
    medium: {
      background: isDark
        ? 'rgba(17, 24, 39, 0.5)'
        : 'rgba(255, 255, 255, 0.5)',
      backdropFilter: 'blur(20px) saturate(170%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)'}`,
      boxShadow: isDark
        ? '0 4px 16px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.04)'
        : '0 4px 16px rgba(91, 95, 227, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
    },
    weak: {
      background: isDark
        ? 'rgba(17, 24, 39, 0.3)'
        : 'rgba(255, 255, 255, 0.35)',
      backdropFilter: 'blur(14px) saturate(140%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)'}`,
    },
  }
}

// ── Theme factory ────────────────────────────────────────────────────────────
function createAppTheme(mode = 'light') {
  const isDark = mode === 'dark'
  const colors = isDark ? { ...modernColors, ...darkColors } : modernColors
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
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
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
    // Coloured shadows for depth instead of flat black
    shadows: [
      'none',
      isDark ? '0 1px 2px 0 rgba(0,0,0,0.3)'          : '0 1px 2px 0 rgba(91,95,227,0.04)',
      isDark ? '0 1px 3px 0 rgba(0,0,0,0.4)'           : '0 1px 3px 0 rgba(91,95,227,0.06)',
      isDark ? '0 4px 6px -1px rgba(0,0,0,0.4)'        : '0 4px 6px -1px rgba(91,95,227,0.06)',
      isDark ? '0 10px 15px -3px rgba(0,0,0,0.5)'      : '0 10px 15px -3px rgba(91,95,227,0.07)',
      isDark ? '0 20px 25px -5px rgba(0,0,0,0.5)'      : '0 20px 25px -5px rgba(91,95,227,0.08)',
      isDark ? '0 25px 50px -12px rgba(0,0,0,0.6)'     : '0 25px 50px -12px rgba(91,95,227,0.10)',
      ...Array(19).fill(isDark ? '0 25px 50px -12px rgba(0,0,0,0.6)' : '0 25px 50px -12px rgba(91,95,227,0.10)'),
    ],
    components: {
      // ── Page background ────────────────────────────────────────────────
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            background: isDark
              ? 'radial-gradient(ellipse at 50% 30%, #1a2030 0%, #0a0f14 100%)'
              : 'radial-gradient(rgba(0,0,0,0.03) 1px, transparent 1px), radial-gradient(ellipse at 50% 30%, #eef1f5 0%, #dce2e9 60%, #d0d7e0 100%)',
            backgroundSize: isDark ? '100% 100%' : '20px 20px, 100% 100%',
            backgroundAttachment: 'fixed',
            minHeight: '100vh',
          },
        },
      },

      // ── Button ─────────────────────────────────────────────────────────
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 10,
            fontWeight: 600,
            padding: '10px 20px',
            transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              transform: 'translateY(-1px)',
            },
            '&:active': {
              transform: 'scale(0.98)',
            },
          },
          contained: {
            boxShadow: `0 4px 14px 0 ${alpha(colors.primary.main, 0.25)}`,
            '&:hover': {
              boxShadow: `0 6px 20px 0 ${alpha(colors.primary.main, 0.35)}`,
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
            boxShadow: `0 4px 14px 0 ${alpha(colors.secondary.main, 0.25)}`,
            '&:hover': {
              background: `linear-gradient(135deg, ${colors.secondary.dark} 0%, ${colors.secondary.main} 100%)`,
              boxShadow: `0 6px 20px 0 ${alpha(colors.secondary.main, 0.35)}`,
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

      // ── Paper — strong frosted glass ───────────────────────────────────
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            backgroundImage: 'none',
            backgroundColor: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            border: glassPresets.strong.border,
          },
          elevation1: {
            boxShadow: isDark
              ? '0 4px 6px -1px rgba(0,0,0,0.2), 0 2px 4px -2px rgba(0,0,0,0.2)'
              : '0 4px 6px -1px rgba(91,95,227,0.04), 0 2px 4px -2px rgba(91,95,227,0.04)',
          },
          elevation2: {
            boxShadow: isDark
              ? '0 10px 15px -3px rgba(0,0,0,0.3), 0 4px 6px -4px rgba(0,0,0,0.3)'
              : '0 10px 15px -3px rgba(91,95,227,0.05), 0 4px 6px -4px rgba(91,95,227,0.05)',
          },
          elevation3: {
            boxShadow: glassPresets.strong.boxShadow,
          },
        },
      },

      // ── Card — glass + hover lift ──────────────────────────────────────
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            backgroundColor: glassPresets.medium.background,
            backdropFilter: glassPresets.medium.backdropFilter,
            border: glassPresets.medium.border,
            boxShadow: glassPresets.medium.boxShadow,
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              boxShadow: isDark
                ? '0 20px 25px -5px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)'
                : '0 20px 25px -5px rgba(91,95,227,0.1), inset 0 1px 0 rgba(255,255,255,0.9)',
              transform: 'translateY(-2px)',
              border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(255, 255, 255, 0.8)'}`,
            },
          },
        },
      },

      // ── AppBar — glass instead of gradient ─────────────────────────────
      MuiAppBar: {
        styleOverrides: {
          root: {
            background: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            boxShadow: glassPresets.strong.boxShadow,
            borderBottom: `2px solid transparent`,
            borderImage: `linear-gradient(90deg, ${colors.primary.main} 0%, ${colors.secondary.main} 100%) 1`,
          },
        },
      },

      // ── Alert ──────────────────────────────────────────────────────────
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

      // ── Chip ───────────────────────────────────────────────────────────
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

      // ── TextField ──────────────────────────────────────────────────────
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

      // ── Select ─────────────────────────────────────────────────────────
      MuiSelect: {
        styleOverrides: {
          root: {
            borderRadius: 10,
          },
        },
      },

      // ── Tabs ───────────────────────────────────────────────────────────
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

      // ── Switch ─────────────────────────────────────────────────────────
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

      // ── Checkbox / Radio ───────────────────────────────────────────────
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

      // ── FAB ────────────────────────────────────────────────────────────
      MuiFab: {
        styleOverrides: {
          root: {
            boxShadow: `0 4px 14px 0 ${alpha(colors.primary.main, 0.3)}`,
          },
          primary: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.primary.light} 100%)`,
          },
          secondary: {
            background: `linear-gradient(135deg, ${colors.secondary.main} 0%, ${colors.secondary.light} 100%)`,
            boxShadow: `0 4px 14px 0 ${alpha(colors.secondary.main, 0.3)}`,
          },
        },
      },

      // ── Tooltip — frosted glass ────────────────────────────────────────
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            borderRadius: 8,
            backgroundColor: glassPresets.medium.background,
            backdropFilter: glassPresets.medium.backdropFilter,
            border: glassPresets.medium.border,
            color: colors.text.primary,
            fontSize: '0.8125rem',
            boxShadow: glassPresets.medium.boxShadow,
          },
        },
      },

      // ── Dialog — glass + blurred backdrop ──────────────────────────────
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: 20,
            backgroundColor: glassPresets.strong.background,
            backdropFilter: glassPresets.strong.backdropFilter,
            border: glassPresets.strong.border,
            boxShadow: glassPresets.strong.boxShadow,
          },
        },
      },
      MuiBackdrop: {
        styleOverrides: {
          root: {
            backdropFilter: 'blur(4px)',
            backgroundColor: isDark ? 'rgba(0,0,0,0.5)' : 'rgba(0,0,0,0.2)',
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

      // ── Progress ───────────────────────────────────────────────────────
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

      // ── Avatar ─────────────────────────────────────────────────────────
      MuiAvatar: {
        styleOverrides: {
          root: {
            background: `linear-gradient(135deg, ${colors.primary.main} 0%, ${colors.secondary.main} 100%)`,
          },
        },
      },

      // ── Badge ──────────────────────────────────────────────────────────
      MuiBadge: {
        styleOverrides: {
          badge: {
            fontWeight: 600,
          },
        },
      },

      // ── Divider — dark-mode-aware ──────────────────────────────────────
      MuiDivider: {
        styleOverrides: {
          root: {
            borderColor: isDark ? alpha('#ffffff', 0.12) : undefined,
          },
        },
      },

      // ── InputLabel (dark-mode focus colour) ────────────────────────────
      MuiInputLabel: {
        styleOverrides: {
          root: isDark ? {
            '&.Mui-focused': {
              color: colors.primary.light,
            },
          } : undefined,
        },
      },

      // ── OutlinedInput (dark-mode border) ───────────────────────────────
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

  // Attach suits & glass presets directly to the theme so components can
  // access them via useTheme() → theme.suits / theme.glass
  theme.suits = colors.suits
  theme.glass = glassPresets

  return theme
}

export { createAppTheme }
export default createAppTheme('light')
