#!/usr/bin/env bun

/**
 * Build script for Chrome extension
 * Bundles popup modules and copies static files
 */

import { copyFileSync, existsSync, mkdirSync, rmSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const isDev = process.argv.includes("--dev");
const isWatch = process.argv.includes("--watch");

// Ensure we're in the chrome-extension directory
process.chdir(__dirname);

const distDir = "dist";
const srcDir = "src";

/**
 * Main build function - can be called repeatedly without side effects
 */
async function build() {
  // Clean dist directory
  if (existsSync(distDir)) {
    rmSync(distDir, { recursive: true });
  }
  mkdirSync(distDir, { recursive: true });

  console.log(
    `Building Chrome extension ${isDev ? "(development)" : "(production)"}...`,
  );

  // Bundle popup.js from modules
  await Bun.build({
    entrypoints: [`${srcDir}/popup/app.js`],
    outdir: distDir,
    naming: "popup.js",
    target: "browser",
    minify: !isDev,
    sourcemap: isDev ? "inline" : "none",
    define: {
      "process.env.NODE_ENV": isDev ? '"development"' : '"production"',
    },
  });

  console.log("[OK] Bundled popup modules");

  // Build CSS with Tailwind
  const cssResult = await Bun.build({
    entrypoints: ["src/popup.css"],
    outdir: distDir,
    naming: "popup.css",
    minify: !isDev,
    loader: {
      ".css": "css",
    },
  });

  // Process CSS with PostCSS/Tailwind
  const postcss = (await import("postcss")).default;
  const tailwindcssPlugin = (await import("@tailwindcss/postcss")).default;
  const autoprefixer = (await import("autoprefixer")).default;

  const cssContent = await Bun.file(join(distDir, "popup.css")).text();
  const result = await postcss([tailwindcssPlugin, autoprefixer]).process(
    cssContent,
    {
      from: join(distDir, "popup.css"),
      to: join(distDir, "popup.css"),
    },
  );

  await Bun.write(join(distDir, "popup.css"), result.css);

  console.log("[OK] Built and processed CSS");

  // Copy static files
  const staticFiles = [
    "manifest.json",
    "popup.html",
    "content.js",
    "icon16.png",
    "icon48.png",
    "icon128.png",
    "xlsx.min.js",
  ];

  for (const file of staticFiles) {
    if (existsSync(file)) {
      copyFileSync(file, join(distDir, file));
    }
  }

  console.log("[OK] Copied static files");

  // Update popup.html in dist to use bundled popup.js
  const popupHtml = await Bun.file(join(distDir, "popup.html")).text();
  const updatedHtml = popupHtml.replace(
    /<script src="popup\/constants\.js"><\/script>\s*<script src="popup\/state\.js"><\/script>\s*<script src="popup\/storage\.js"><\/script>\s*<script src="popup\/ui\.js"><\/script>\s*<script src="popup\/excel\.js"><\/script>\s*<script src="popup\/form\.js"><\/script>\s*<script src="popup\/navigation\.js"><\/script>\s*<script src="popup\/settings\.js"><\/script>\s*<script src="popup\/confirmation\.js"><\/script>\s*<script src="popup\/acgme\.js"><\/script>\s*<script src="popup\/app\.js"><\/script>/,
    '<script src="popup.js"></script>',
  );
  await Bun.write(join(distDir, "popup.html"), updatedHtml);

  console.log("[OK] Updated popup.html");

  console.log(`\n[SUCCESS] Build complete! Extension ready in ${distDir}/`);
}

// Run initial build
await build();

if (isWatch) {
  console.log("\n[WATCH] Watching for changes...");
  const watcher = Bun.watch("src");

  // Debounce rebuilds to prevent multiple rapid rebuilds
  let rebuildTimer = null;

  for await (const event of watcher) {
    console.log(`\n[WATCH] Change detected...`, event);

    // Clear existing timer and set a new one
    if (rebuildTimer) {
      clearTimeout(rebuildTimer);
    }

    rebuildTimer = setTimeout(async () => {
      await build();
      rebuildTimer = null;
    }, 100); // 100ms debounce
  }
}
