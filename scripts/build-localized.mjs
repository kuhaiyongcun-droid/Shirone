import { execFileSync } from "node:child_process";
import { mkdir, rename, rm } from "node:fs/promises";
import { resolve } from "node:path";

// Separate processes prevent the integration's configuration cache from
// carrying one locale into the next build. Both builds use the same content.
const root = process.cwd();
const astro = resolve(root, "node_modules/astro/bin/astro.mjs");
const staging = resolve(root, ".localized-build");
const output = resolve(root, "dist");

function run(script, args = [], env = process.env) {
	execFileSync(process.execPath, [script, ...args], {
		cwd: root,
		env,
		stdio: "inherit",
	});
}

await rm(staging, { recursive: true, force: true });
await mkdir(staging, { recursive: true });
try {
	run(resolve(root, "scripts/content/sync.mjs"));
	for (const [locale, base, destination] of [
		["zh_CN", "/", output],
		["en", "/en/", resolve(staging, "en")],
	]) {
		console.log(`\n[localization] Building ${locale} at ${base}`);
		run(astro, ["build", "--outDir", destination], {
			...process.env,
			PUBLIC_SHIRONE_LOCALE: locale,
			PUBLIC_SHIRONE_BASE: base,
		});
		run(resolve(root, "node_modules/pagefind/lib/runner/bin.cjs"), ["--site", destination]);
		run(resolve(root, "scripts/fonts/check-fonts.mjs"), [], {
			...process.env,
			FONT_DIST_DIR: destination,
			PUBLIC_SHIRONE_BASE: base,
			PUBLIC_SHIRONE_LOCALE: locale,
		});
	}
	await rename(resolve(staging, "en"), resolve(output, "en"));
	run(resolve(root, "scripts/check-localization.mjs"));
} finally {
	await rm(staging, { recursive: true, force: true });
}
