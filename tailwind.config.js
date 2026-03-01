/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/index.html'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        display: ['Fraunces', 'serif'],
        body: ['Sora', 'sans-serif'],
      },
      colors: {
        sand: '#f6f1e8',
        ink: '#1d232b',
        accent: '#0f766e',
        accentDark: '#0a5f5a',
      },
      boxShadow: {
        glow: '0 20px 60px rgba(20, 24, 30, 0.18)',
      },
    },
  },
  plugins: [],
};
