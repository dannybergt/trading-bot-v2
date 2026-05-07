/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Brand palette inferred from the legacy NexusPulse Trade bundle.
        // Tune in src/styles.css if/when exact values are recovered.
        "bergt-green": {
          DEFAULT: "#22c55e",
          50: "#f0fdf4",
          400: "#4ade80",
          500: "#22c55e",
          600: "#16a34a",
          700: "#15803d",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
