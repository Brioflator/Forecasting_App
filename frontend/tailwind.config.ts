import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        actual: "#2563eb",
        forecast: "#db2777",
        band: "#db2777",
      },
    },
  },
  plugins: [],
};

export default config;
