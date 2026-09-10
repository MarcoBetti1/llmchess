import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
export default defineConfig([
  ...nextVitals,
  // Legacy API normalization intentionally accepts provider-shaped payloads.
  { rules: { "react-hooks/set-state-in-effect": "off", "react-hooks/refs": "off", "react-hooks/purity": "off" } },
  globalIgnores([".next/**", "out/**", "next-env.d.ts"])
]);
