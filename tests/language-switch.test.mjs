import assert from "node:assert/strict";
import test from "node:test";
import { languageSwitchUrl } from "../src/utils/language-switch.mjs";

test("switching preserves the current article, encoded route, filters and anchor", () => {
	const current = "https://blog.example/posts/%E4%BD%A0%E5%A5%BD/?tag=Astro#reading";
	assert.equal(languageSwitchUrl(current, "en"), "/en/posts/%E4%BD%A0%E5%A5%BD/?tag=Astro#reading");
	assert.equal(languageSwitchUrl(`https://blog.example${languageSwitchUrl(current, "en")}`, "zh_CN"), "/posts/%E4%BD%A0%E5%A5%BD/?tag=Astro#reading");
});

test("home, locale root and similarly named content routes stay valid", () => {
	assert.equal(languageSwitchUrl("/", "en"), "/en/");
	assert.equal(languageSwitchUrl("/en", "zh_CN"), "/");
	assert.equal(languageSwitchUrl("/en/", "zh_CN"), "/");
	assert.equal(languageSwitchUrl("/en/enjoy/", "zh_CN"), "/enjoy/");
	assert.equal(languageSwitchUrl("/enjoy/", "en"), "/en/enjoy/");
	assert.equal(languageSwitchUrl("/en/archive/?category=Tech", "en"), "/en/archive/?category=Tech");
	assert.equal(languageSwitchUrl("/404/", "en"), "/en/404.html");
	assert.equal(languageSwitchUrl("/en/404/", "zh_CN"), "/404.html");
});
