/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-display)", "ui-sans-serif", "system-ui"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular"],
      },
      colors: {
        background: {
          DEFAULT: "rgb(var(--background) / <alpha-value>)",
          subtle: "rgb(var(--background-subtle) / <alpha-value>)",
          muted: "rgb(var(--background-muted) / <alpha-value>)",
          elevated: "rgb(var(--background-elevated) / <alpha-value>)",
          overlay: "rgb(var(--background-overlay) / <alpha-value>)",
        },
        foreground: {
          DEFAULT: "rgb(var(--foreground) / <alpha-value>)",
          muted: "rgb(var(--foreground-muted) / <alpha-value>)",
          subtle: "rgb(var(--foreground-subtle) / <alpha-value>)",
          inverse: "rgb(var(--foreground-inverse) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--border) / <alpha-value>)",
          muted: "rgb(var(--border-muted) / <alpha-value>)",
          strong: "rgb(var(--border-strong) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          hover: "rgb(var(--primary-hover) / <alpha-value>)",
          foreground: "rgb(var(--primary-foreground) / <alpha-value>)",
        },
        scrim: "rgb(var(--overlay-scrim) / <alpha-value>)",
        success: "rgb(var(--success) / <alpha-value>)",
        warning: "rgb(var(--warning) / <alpha-value>)",
        error: "rgb(var(--error) / <alpha-value>)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        soft: "var(--shadow-sm)",
        card: "var(--shadow-md)",
      },
      borderRadius: {
        xl: "1.25rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: 0, transform: "translateY(16px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.7 },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        "pulse-soft": "pulse-soft 2.8s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
