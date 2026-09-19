// Production build: esbuild bundle + content-hashed assets + generated index.html.
import { build, context } from "esbuild";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";

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

async function finish() {
  const js = readFileSync("dist/assets/app.js");
  // Tailwind runs over the design system so utilities are available alongside it.
  // Preflight is deliberately not imported (see styles.css) - its reset would
  // fight the hand-built component classes every page already uses.
  const source = readFileSync("src/styles.css", "utf8");
  const processed = await postcss([tailwindcss()]).process(source, { from: "src/styles.css", to: "dist/assets/app.css" });
  const css = Buffer.from(processed.css);
  const jh = createHash("sha256").update(js).digest("hex").slice(0, 10);
  const ch = createHash("sha256").update(css).digest("hex").slice(0, 10);
  writeFileSync(`dist/assets/app-${jh}.js`, js);
  writeFileSync(`dist/assets/app-${ch}.css`, css);
  const html = readFileSync("index.html", "utf8").replace("%JS%", `/assets/app-${jh}.js`).replace("%CSS%", `/assets/app-${ch}.css`);
  writeFileSync("dist/index.html", html);
  if (!watch) rmSync("dist/assets/app.js", { force: true });
  if (existsSync("public")) cpSync("public", "dist", { recursive: true });
  // pdf.js runs page parsing in a worker; PdfPreview loads it from /assets/pdf.worker.min.js.
  cpSync("node_modules/pdfjs-dist/build/pdf.worker.min.js", "dist/assets/pdf.worker.min.js");
  cpSync("node_modules/pdfjs-dist/standard_fonts", "dist/assets/standard_fonts", { recursive: true });
}

if (watch) {
  const ctx = await context({ ...options, plugins: [{ name: "finish", setup(b) { b.onEnd(async () => { try { await finish(); } catch (e) { console.error(e); } }); } }] });
  await ctx.watch();
} else {
  await build(options);
  await finish();
}
