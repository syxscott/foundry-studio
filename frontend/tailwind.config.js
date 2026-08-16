/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Scientific / lab-style accent palette.
        brand: {
          50: "#eef6ff",
          100: "#d9ecff",
          200: "#bcdcff",
          300: "#8ec6ff",
          400: "#5aa6f0",
          500: "#2b6cb0",
          600: "#225a94",
          700: "#1c4b7c",
          800: "#173c64",
          900: "#123050",
        },
        // Cyan accent used for gradients / highlights.
        accent: {
          50: "#ecfeff",
          100: "#cffafe",
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
        surface: {
          DEFAULT: "#ffffff",
          alt: "#f6f9fc",
          border: "#e2e8f0",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Noto Sans SC",
          "Noto Sans JP",
          "Noto Sans KR",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(16,24,40,0.05), 0 1px 3px rgba(16,24,40,0.1)",
        card: "0 1px 2px rgba(16,24,40,0.04), 0 4px 12px rgba(16,24,40,0.06)",
        glow: "0 8px 30px rgba(34,90,148,0.18)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "spin-slow": {
          "100%": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out both",
        "spin-slow": "spin-slow 1s linear infinite",
      },
    },
  },
  plugins: [],
};
