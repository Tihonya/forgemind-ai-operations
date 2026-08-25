import type { Config } from 'tailwindcss'
import tailwindcssAnimate from 'tailwindcss-animate'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Semantic design tokens (WP-UX-UA-02) ─────────────────────────
        // These resolve the HSL custom properties defined in src/index.css
        // and are the canonical way to reference theme values in changed
        // surfaces. They exist alongside (not instead of) the `primary` and
        // `steel` palettes so existing screens keep rendering while the UI
        // primitives (Button, Card, Alert, …) resolve their semantic names.
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        // Semantic feedback colors (never the sole carrier of meaning).
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning))',
          foreground: 'hsl(var(--warning-foreground))',
        },
        info: {
          DEFAULT: 'hsl(var(--info))',
          foreground: 'hsl(var(--info-foreground))',
        },
        // ── Industrial palette (pre-existing; retained for compatibility) ──
        steel: {
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
          950: '#020617',
        },
      },
      borderRadius: {
        // Radius scale anchored to --radius (index.css).
        sm: 'calc(var(--radius) - 2px)',
        md: 'var(--radius)',
        lg: 'calc(var(--radius) + 2px)',
        xl: 'calc(var(--radius) + 4px)',
      },
      // Responsive content container widths (mobile-first). `container` is
      // disabled by default in Tailwind v3; these are explicit token widths
      // used by the shared Container component.
      maxWidth: {
        'content': '80rem', // 1280px — widest operational layout
        'content-narrow': '64rem', // 1024px — reading/forms
      },
      boxShadow: {
        // Elevation scale for surfaces (calm, low-contrast — no heavy shadows).
        'surface': '0 1px 2px 0 rgb(0 0 0 / 0.3)',
        'surface-md': '0 4px 6px -1px rgb(0 0 0 / 0.3)',
        'drawer': '0 8px 24px -6px rgb(0 0 0 / 0.5)',
      },
    },
  },
  plugins: [tailwindcssAnimate],
} satisfies Config
