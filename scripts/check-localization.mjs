import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { build } from "esbuild";
import { fromHtml } from "hast-util-from-html";
import { languageSwitchUrl } from "../src/utils/language-switch.mjs";

const root = process.cwd();
const output = resolve(root, "dist");
const keys = [...(await readFile(join(root, "src/i18n/i18nKey.ts"), "utf8"))
	.matchAll(/^\s*\w+\s*=\s*"(\w+)"/gm)].map((match) => match[1]);
const locales = ["en", "es", "id", "ja", "ko", "th", "tr", "vi", "zh_CN", "zh_TW"];
const dictionaries = {};
for (const locale of locales) {
	const bundled = await build({
		entryPoints: [join(root, `src/i18n/languages/${locale}.ts`)],
		bundle: true,
		write: false,
		format: "esm",
		platform: "node",
	});
	dictionaries[locale] = (await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`))[locale];
	assert.deepEqual(Object.keys(dictionaries[locale]).sort(), [...keys].sort(), `${locale}: dictionary keys must match`);
	for (const key of keys) {
		assert.ok(dictionaries[locale][key]?.trim(), `${locale}.${key}: empty translation`);
		const placeholders = (text) => [...new Set(text.match(/\{\w+\}/g) || [])].sort();
		assert.deepEqual(placeholders(dictionaries[locale][key]), placeholders(dictionaries.en[key]), `${locale}.${key}: placeholder mismatch`);
	}
}

async function htmlFiles(directory) {
	const files = [];
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const file = join(directory, entry.name);
		if (entry.isDirectory() && !(directory === output && entry.name === "en")) files.push(...await htmlFiles(file));
		else if (entry.isFile() && entry.name.endsWith(".html")) files.push(file);
	}
	return files;
}

function walk(node, callback) {
	callback(node);
	for (const child of node.children || []) walk(child, callback);
}

let pageCount = 0;
for (const [locale, directory, prefix] of [["zh_CN", output, "/"], ["en", join(output, "en"), "/en/"]]) {
	assert.ok(existsSync(join(directory, "pagefind/pagefind.js")), `${locale}: search bundle missing`);
	const files = await htmlFiles(directory);
	for (const file of files) {
		const html = await readFile(file, "utf8");
		if (/http-equiv="refresh"/i.test(html)) continue;
		const route = `${prefix}${relative(directory, file).replace(/index\.html$/, "").replaceAll("\\", "/")}`;
		let languageSwitch;
		walk(fromHtml(html), (node) => {
			if (node.type !== "element") return;
			const attrs = node.properties || {};
			if (node.tagName === "html") assert.equal(attrs.lang, locale.replace("_", "-"), `${route}: document language`);
			if (attrs.id === "language-switch") languageSwitch = attrs;
			// Verify generated assets exist at their actual deployed paths.
			const reference = node.tagName === "script" || node.tagName === "img" ? attrs.src
				: node.tagName === "link" && attrs.rel?.includes("stylesheet") ? attrs.href : undefined;
			if (typeof reference === "string" && reference.startsWith("/") && !reference.startsWith("//")) {
				assert.ok(existsSync(join(output, decodeURIComponent(reference.split(/[?#]/)[0]))), `${route}: missing asset ${reference}`);
			}
		});
		assert.ok(languageSwitch, `${route}: language switch missing`);
		assert.equal(languageSwitch.ariaLabel, dictionaries[locale].languageSwitch, `${route}: switch accessible name`);
		assert.equal(languageSwitch.href, languageSwitchUrl(route, locale === "en" ? "zh_CN" : "en"), `${route}: switch destination`);
		const alternate = join(output, languageSwitch.href, languageSwitch.href.endsWith(".html") ? "" : "index.html");
		assert.ok(existsSync(alternate), `${route}: alternate page missing`);
		assert.ok(html.includes(dictionaries[locale].allRightsReserved), `${route}: footer language`);
		assert.ok(html.includes(dictionaries[locale].sitemap), `${route}: sitemap language`);
		pageCount++;
	}
}
console.log(`[localization] All ${locales.length} dictionaries and ${pageCount} localized pages passed; assets and search bundles exist.`);
