/** Switch only the locale prefix; preserve the route, query and fragment. */
export function languageSwitchUrl(currentUrl, targetLanguage) {
	const current = new URL(currentUrl, "https://shirone.invalid");
	let route = current.pathname.replace(/^\/en(?=\/|$)/, "") || "/";
	// Astro prerenders the /404/ route as 404.html.
	if (route === "/404/") route = "/404.html";
	const localized = targetLanguage === "en" ? `/en${route}` : route;
	return `${localized}${current.search}${current.hash}`;
}
