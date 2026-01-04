module.exports = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow raw color values in className",
    },
    schema: [],
  },
  create(context) {
    const RAW_COLOR_PATTERNS = [
      /\b(bg|text|border|ring|shadow)-(gray|blue|red|green|yellow|slate|zinc|neutral|stone|emerald|teal|indigo|purple|pink)-\d+/,
      /\b(bg|text|border)-\[(#|rgb|hsl)/,
      /\bfrom-(gray|blue|red|green|yellow)-\d+/,
    ];

    const SEMANTIC_PATTERNS = [
      /\b(bg|text|border)-(background|foreground|primary|success|warning|error|border|scrim)/,
    ];

    return {
      JSXAttribute(node) {
        if (node.name.name !== "className") return;

        const value = node.value?.value || "";

        for (const pattern of RAW_COLOR_PATTERNS) {
          if (pattern.test(value)) {
            const isSemanticColor = SEMANTIC_PATTERNS.some((semantic) => semantic.test(value));
            if (!isSemanticColor) {
              context.report({
                node,
                message: `Use semantic color tokens instead of raw colors. Found: ${value.match(pattern)?.[0]}`,
              });
            }
          }
        }
      },
    };
  },
};
