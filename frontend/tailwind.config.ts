import type { Config } from "tailwindcss";

// Light, soft palette: sage green on warm white, apricot for warnings, coral for breaches.
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F4F6F1",
        surface: "#FFFFFF",
        line: "#E1E8DE",
        ink: { DEFAULT: "#1E2A21", 2: "#3C4A40", muted: "#56655A" },
        sage: {
          50: "#EEF2EC",
          100: "#E6EFE4",
          200: "#DCE8D9",
          300: "#BCD3B8",
          400: "#7FA884",
          500: "#5E8A66",
          600: "#3F6247",
          700: "#2B4632",
        },
        apricot: { 100: "#FBE9D5", 400: "#E8A96B", 700: "#8A4B12" },
        coral: { 100: "#F8DED7", 400: "#D9785F", 700: "#9A3B26" },
        sky: { 100: "#E3EEF3", 400: "#8FB6C9", 700: "#2F5B70" },
        lilac: { 400: "#B7A3D1" },
        sand: { 400: "#D9C27A" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: { card: "20px" },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        grow: { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
      },
      animation: {
        rise: "rise 400ms ease-out both",
        grow: "grow 700ms cubic-bezier(.2,.8,.2,1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
