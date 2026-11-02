/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--bg)", surface: "var(--surface)", muted: "var(--muted)",
        ink: "var(--text)", accent: "var(--accent)", line: "var(--border)",
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', "monospace"],
      },
    },
  },
  plugins: [],
};
