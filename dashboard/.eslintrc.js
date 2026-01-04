module.exports = {
  extends: ["next/core-web-vitals"],
  plugins: ["local-rules"],
  rules: {
    "local-rules/no-raw-colors": "error",
  },
};
