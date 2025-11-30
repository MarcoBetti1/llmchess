import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["\"Space Grotesk\"", "Inter", "system-ui", "sans-serif"]
      },
      colors: {
        canvas: {
          900: "#0b1024",
          800: "#101734",
          700: "#1b254b",
          600: "#2a355f"
        },
        accent: "#7ce7ac",
        accent2: "#a3bffa",
        boardLight: "#f8fafc",
        boardDark: "#0f172a"
      },
      boxShadow: {
        glow: "0 10px 45px -20px rgba(124, 231, 172, 0.65)"
      }
    }
  },
  plugins: []
};

export default config;
