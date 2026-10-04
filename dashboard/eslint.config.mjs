import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Money is decimal text. Format it with lib/money.ts, never parse it into a float.
    rules: {
      "no-restricted-globals": ["error", { name: "parseFloat", message: "Use lib/money.ts for money." }],
      "no-restricted-properties": ["error", { object: "Number", property: "parseFloat", message: "Use lib/money.ts for money." }],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
