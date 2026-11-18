/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "SF Pro",
          "Inter",
          "Helvetica Neue",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "SF Pro",
          "Inter",
          "Helvetica Neue",
          "system-ui",
          "sans-serif",
        ],
        mono: ["Geist Mono", "SF Mono", "ui-monospace", "Menlo", "monospace"],
      },
      fontSize: {
        display: [
          "3.75rem",
          { lineHeight: "1.05", fontWeight: "700", letterSpacing: "-0.035em" },
        ],
        title: [
          "2.5rem",
          { lineHeight: "1.08", fontWeight: "700", letterSpacing: "-0.03em" },
        ],
        subtitle: [
          "1.875rem",
          { lineHeight: "1.15", fontWeight: "700", letterSpacing: "-0.02em" },
        ],
        heading: [
          "1.5rem",
          { lineHeight: "1.25", fontWeight: "700", letterSpacing: "-0.02em" },
        ],
        subheading: [
          "1.25rem",
          { lineHeight: "1.35", fontWeight: "650", letterSpacing: "-0.01em" },
        ],
        section: [
          "0.75rem",
          { lineHeight: "1.4", fontWeight: "700", letterSpacing: "0.09em" },
        ],
        body: ["1.0625rem", { lineHeight: "1.62", fontWeight: "400", letterSpacing: "-0.012em" }],
        bodyLarge: ["1.3125rem", { lineHeight: "1.45", fontWeight: "400", letterSpacing: "-0.018em" }],
        small: ["0.875rem", { lineHeight: "1.55", fontWeight: "500" }],
      },
      colors: {
        white: "#FFFFFF",
        black: "#000000",
        neutral900: "#1D1D1F",
        neutral800: "#2C2C2E",
        neutral700: "#3A3A3C",
        neutral600: "#48484A",
        gray500: "#6E6E73",
        gray400: "#86868B",
        gray300: "#D2D2D7",
        gray200: "#E8E8ED",
        gray100: "#F5F5F7",
        gray50: "#FBFBFD",
        stone50: "#F5F5F7",
        stone100: "#EFEFF2",
        stone200: "#E8E8ED",
        stone300: "#D2D2D7",
        accent: {
          50: "#EEF5FF",
          100: "#DCEBFF",
          200: "#B8D7FF",
          300: "#7DB8FF",
          400: "#2997FF",
          500: "#0071E3",
          600: "#0066CC",
          700: "#0058B0",
          800: "#004A94",
          900: "#003A75",
        },
        success: {
          50: "#ECFDF3",
          100: "#D1FADF",
          500: "#17B26A",
          600: "#079455",
          700: "#067647",
        },
        danger: "#E30000",
        primary: "#1D1D1F",
        secondary: "#2C2C2E",
        background: "#FFFFFF",
        backgroundAlt: "#FFFFFF",
        textPrimary: "var(--text-primary)",
        textSecondary: "var(--text-secondary)",
        textTertiary: "var(--text-tertiary)",
        border: "#E8E8ED",
        borderLight: "#F5F5F7",
        selected: "#EEF5FF",
        blue500: "#0071E3",
        blue600: "#0066CC",
      },
      // Borders stay whisper-quiet: separation comes from space and soft
      // surfaces, not outlines (same rule as the Markdown reading theme).
      borderColor: {
        neutral900: "#2C2C2E",
        neutral800: "#262628",
        neutral700: "#262628",
        neutral600: "#333336",
        gray300: "#E0E0E5",
        gray200: "#ECECF0",
        gray100: "#F2F2F5",
        stone300: "#E0E0E5",
        stone200: "#ECECF0",
        stone100: "#F2F2F5",
        border: "#ECECF0",
        borderLight: "#F2F2F5",
        stone: {
          100: "#F2F2F5",
          200: "#ECECF0",
          300: "#E0E0E5",
        },
      },
      backgroundImage: {
        "gradient-hero":
          "linear-gradient(180deg, #ffffff 0%, #f5f5f7 100%)",
        "gradient-subtle":
          "linear-gradient(180deg, rgba(29, 29, 31, 0.03) 0%, rgba(29, 29, 31, 0) 100%)",
        "gradient-panel":
          "linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(245, 245, 247, 0.92) 100%)",
        "gradient-dark-panel":
          "linear-gradient(180deg, rgba(29, 29, 31, 0.96) 0%, rgba(22, 22, 23, 0.96) 100%)",
      },
      boxShadow: {
        soft: "0 18px 40px -28px rgba(15, 23, 42, 0.28)",
        professional:
          "0 20px 60px -32px rgba(15, 23, 42, 0.28), 0 10px 18px -14px rgba(15, 23, 42, 0.18)",
        panel:
          "0 26px 70px -36px rgba(15, 23, 42, 0.34), 0 12px 24px -18px rgba(15, 23, 42, 0.18)",
        glow: "0 18px 40px -20px rgba(0, 113, 227, 0.28)",
      },
      borderRadius: {
        xl: "0.625rem",
        "2xl": "0.75rem",
        "3xl": "1rem",
        "4xl": "1.25rem",
      },
      spacing: {
        18: "4.5rem",
        88: "22rem",
        100: "25rem",
        112: "28rem",
        128: "32rem",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.28s ease-out",
        "fade-in-up": "fade-in-up 0.4s ease-out",
        "scale-in": "scale-in 0.24s ease-out",
      },
    },
  },
  plugins: [],
};
