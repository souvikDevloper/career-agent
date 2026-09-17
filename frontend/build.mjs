// Production build: esbuild bundle + content-hashed assets + generated index.html.
import { build, context } from "esbuild";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const watch = process.argv.includes("--watch");
rmSync("dist", { recursive: true, force: true });
mkdirSync("dist/assets", { recursive: true });

const options = {
  entryPoints: ["src/main.tsx"],
  bundle: true,
  minify: !watch,
  sourcemap: watch ? "inline" : false,
  format: "esm",
  target: ["es2020", "chrome100", "safari15"],
  outdir: "dist/assets",
  entryNames: "app",
  loader: { ".svg": "text" },
  define: { "process.env.NODE_ENV": JSON.stringify(watch ? "development" : "production") },
  jsx: "automatic",
  logLevel: "info",
};

function finish() {
  const js = readFileSync("dist/assets/app.js");
  const css = readFileSync("src/styles.css");
  const jh = createHash("sha256").update(js).digest("hex").slice(0, 10);
  const ch = createHash("sha256").update(css).digest("hex").slice(0, 10);
  writeFileSync(`dist/assets/app-${jh}.js`, js);
  writeFileSync(`dist/assets/app-${ch}.css`, css);
  const html = readFileSync("index.html", "utf8").replace("%JS%", `/assets/app-${jh}.js`).replace("%CSS%", `/assets/app-${ch}.css`);
  writeFileSync("dist/index.html", html);
  if (!watch) rmSync("dist/assets/app.js", { force: true });
  if (existsSync("public")) cpSync("public", "dist", { recursive: true });
}

if (watch) {
  const ctx = await context({ ...options, plugins: [{ name: "finish", setup(b) { b.onEnd(() => finish()); } }] });
  await ctx.watch();
} else {
  await build(options);
  finish();
}
