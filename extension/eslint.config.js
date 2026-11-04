import js from "@eslint/js";
import globals from "globals";
export default [
  { ignores: ["vendor/**", "node_modules/**"] },
  js.configs.recommended,
  { languageOptions: { ecmaVersion: 2022, sourceType: "module", globals: { ...globals.browser, ...globals.serviceworker, ...globals.node, chrome: "readonly", ort: "readonly" } },
    rules: { "no-unused-vars": ["error", { argsIgnorePattern: "^_" }], eqeqeq: "error", "no-var": "error", "prefer-const": "error", "no-eval": "error", "no-implied-eval": "error", "no-new-func": "error" } },
];
