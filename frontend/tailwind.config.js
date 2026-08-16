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
          500: "#2b6cb0",
          600: "#225a94",
          700: "#1c4b7c",
        },
        surface: {
          DEFAULT: "#ffffff",
          alt: "#f7f9fc",
          border: "#e2e8f0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Noto Sans SC", "Noto Sans JP", "Noto Sans KR", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
