// Use a local package-manager check; never fetch an executable during install.
if (!(process.env.npm_config_user_agent || "").startsWith("pnpm/")) {
	console.error("Install this project with pnpm using its frozen lockfile.");
	process.exitCode = 1;
}
