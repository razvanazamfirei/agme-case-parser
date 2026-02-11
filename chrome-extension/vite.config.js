import { crx } from "@crxjs/vite-plugin";
import { defineConfig } from "vite";
import manifest from "./manifest.json";

export default defineConfig({
  plugins: [crx({ manifest })],
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: process.env.NODE_ENV === "development" ? "inline" : false,
    minify: process.env.NODE_ENV !== "development",
  },
  css: {
    postcss: "./postcss.config.js",
  },
});
