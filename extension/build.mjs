// Builds dist/chromium and dist/firefox from the same sources.
import { cp, mkdir, rm, writeFile, readFile } from "node:fs/promises";
import { context, build } from "esbuild";

const watch = process.argv.includes("--watch");
const targets = {
  chromium: { manifest: "manifest.chromium.json", target: "chrome116" },
  firefox: { manifest: "manifest.firefox.json", target: "firefox128" },
};

for (const [name, t] of Object.entries(targets)) {
  const out = `dist/${name}`;
  await rm(out, { recursive: true, force: true });
  await mkdir(out, { recursive: true });
  await cp("static", out, { recursive: true });
  // pt_PT and other Portuguese variants fall back to "pt" before English.
  await cp(`${out}/_locales/pt_BR`, `${out}/_locales/pt`, { recursive: true });
  await writeFile(`${out}/manifest.json`, await readFile(t.manifest));
  const options = {
    entryPoints: { background: "src/background.ts", popup: "src/popup.ts" },
    bundle: true,
    format: "esm",
    target: t.target,
    outdir: out,
    sourcemap: false,
    minify: false, // reviewers of the store listings read this code
    legalComments: "none",
    define: { __BROWSER__: JSON.stringify(name) },
    logLevel: "info",
  };
  if (watch) await (await context(options)).watch();
  else await build(options);
}
