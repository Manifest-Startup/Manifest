/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Manrope",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        display: ["Newsreader", "Georgia", "serif"],
      },
      fontSize: {
        display: [
          "3.75rem",
          { lineHeight: "1.02", fontWeight: "700", letterSpacing: "-0.04em" },
        ],
        title: [
          "2.5rem",
          { lineHeight: "1.08", fontWeight: "700", letterSpacing: "-0.03em" },
        ],
        subtitle: [
          "1.875rem",
          { lineHeight: "1.18", fontWeight: "650", letterSpacing: "-0.02em" },
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
          "1rem",
          { lineHeight: "1.5", fontWeight: "700", letterSpacing: "0.04em" },
        ],
        body: ["1rem", { lineHeight: "1.7", fontWeight: "400" }],
        bodyLarge: ["1.125rem", { lineHeight: "1.75", fontWeight: "400" }],
        small: ["0.875rem", { lineHeight: "1.55", fontWeight: "500" }],
      },
      colors: {
        white: "#FFFFFF",
        black: "#000000",
        neutral900: "#16212C",
        neutral800: "#1F2D3B",
        neutral700: "#324252",
        neutral600: "#51606F",
        gray500: "#6C7785",
        gray400: "#96A0AB",
        gray300: "#CDD4DB",
        gray200: "#E4E8EC",
        gray100: "#F3F5F7",
        gray50: "#FAFBFC",
        stone50: "#F7F7F5",
        stone100: "#F0F0EE",
        stone200: "#E7E7E5",
        stone300: "#D4D4D1",
        accent: {
          50: "#ECF1FF",
          100: "#DCE6FF",
          200: "#BDD0FF",
          300: "#8FAEFF",
          400: "#5E86FF",
          500: "#2F62E8",
          600: "#214BC4",
          700: "#1B3C9B",
          800: "#19357C",
          900: "#192F63",
        },
        success: {
          50: "#ECFDF3",
          100: "#D1FADF",
          500: "#17B26A",
          600: "#079455",
          700: "#067647",
        },
        danger: "#D92D20",
        primary: "#16212C",
        secondary: "#1F2D3B",
        background: "#FFFFFF",
        backgroundAlt: "#FFFFFF",
        textPrimary: "var(--text-primary)",
        textSecondary: "var(--text-secondary)",
        textTertiary: "var(--text-tertiary)",
        border: "#E7E7E5",
        borderLight: "#F0F0EE",
        selected: "#ECF1FF",
        blue500: "#2F62E8",
        blue600: "#214BC4",
      },
      backgroundImage: {
        "gradient-hero":
          "radial-gradient(circle at 12% 18%, rgba(47, 98, 232, 0.16), transparent 28%), radial-gradient(circle at 82% 12%, rgba(255, 255, 255, 0.85), transparent 24%), linear-gradient(180deg, #fbf8f3 0%, #f2ede6 100%)",
        "gradient-subtle":
          "linear-gradient(180deg, rgba(22, 33, 44, 0.03) 0%, rgba(22, 33, 44, 0) 100%)",
        "gradient-panel":
          "linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 244, 238, 0.9) 100%)",
        "gradient-dark-panel":
          "linear-gradient(180deg, rgba(24, 33, 45, 0.96) 0%, rgba(18, 23, 31, 0.96) 100%)",
      },
      boxShadow: {
        soft: "0 18px 40px -28px rgba(15, 23, 42, 0.28)",
        professional:
          "0 20px 60px -32px rgba(15, 23, 42, 0.28), 0 10px 18px -14px rgba(15, 23, 42, 0.18)",
        panel:
          "0 26px 70px -36px rgba(15, 23, 42, 0.34), 0 12px 24px -18px rgba(15, 23, 42, 0.18)",
        glow: "0 18px 40px -20px rgba(47, 98, 232, 0.28)",
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
