import { defineConfig } from "astro/config";

export default defineConfig({
  output: "static",
  devToolbar: { enabled: false },
  site: process.env.SITE_URL || "http://localhost:4321",
  base: process.env.BASE_PATH || "/",
});
