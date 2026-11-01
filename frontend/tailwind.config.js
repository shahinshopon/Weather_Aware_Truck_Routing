/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        risk: {
          low: "#10b981",
          moderate: "#eab308",
          high: "#f97316",
          severe: "#ef4444",
          notravel: "#7f1d1d",
          unknown: "#64748b",
        },
      },
    },
  },
  plugins: [],
};
