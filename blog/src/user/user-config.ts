/**
 * 用户配置覆盖层（由 `pnpm content:sync` 生成，请勿手工编辑）。
 *
 * 内容来自内容仓的以下文件，改配置请改那边：
 * - config/site.yaml
 * - config/profile.yaml
 * - config/announcement.yaml
 * - config/post-list.yaml
 * - config/comment.yaml
 * - config/context-menu.yaml
 * - config/sidebar.yaml
 * - config/footer.yaml
 * - config/skills.yaml
 * - config/projects.yaml
 * - config/timeline.yaml
 * - config/devices.yaml
 * - config/games.yaml
 * - config/music.yaml
 * - config/anime.yaml
 * - config/font.yaml
 * - config/llms.yaml
 * - config/umami.yaml
 * - config/about.yaml
 * - config/friends.yaml
 * - config/moments.yaml
 * - config/albums.yaml
 * - config/compass.yaml
 * - config/series.yaml
 * - config/nav-bar.yaml
 *
 * 每个领域的类型标注让 `tsc` 直接校验用户配置：拼错的键、越界的枚举、填错的类型
 * 都会在这里报错，错误信息里的行号可以对回上面的 YAML 文件。
 */

import type { AboutConfig } from "@/types/aboutConfig";
import type { AlbumsConfig } from "@/types/albumsConfig";
import type { AnimeConfig } from "@/types/animeConfig";
import type { AnnouncementConfig } from "@/types/announcementConfig";
import type { CommentConfig } from "@/types/commentConfig";
import type { CompassConfig } from "@/types/compassConfig";
import type { ProfileConfig, SiteConfig } from "@/types/config";
import type { ContextMenuConfig } from "@/types/contextMenuConfig";
import type { DevicesConfig } from "@/types/devicesConfig";
import type { FontConfig } from "@/types/fontConfig";
import type { FooterConfig } from "@/types/footerConfig";
import type { FriendsConfig } from "@/types/friendsConfig";
import type { GamesConfig } from "@/types/gamesConfig";
import type { LlmsConfig } from "@/types/llmsConfig";
import type { MomentsConfig } from "@/types/momentsConfig";
import type { MusicConfig } from "@/types/musicConfig";
import type { NavBarConfigOverride } from "@/types/navBarConfig";
import type { PostListConfig } from "@/types/postListConfig";
import type { ProjectsConfig } from "@/types/projectsConfig";
import type { SeriesConfig } from "@/types/seriesConfig";
import type { SidebarConfig } from "@/types/sidebarConfig";
import type { SkillsConfig } from "@/types/skillsConfig";
import type { TimelineConfig } from "@/types/timelineConfig";
import type { UmamiConfig } from "@/types/umamiConfig";

/**
 * 用户只需要写想改的键，因此每个领域都按「深度可选」校验。
 *
 * 数组保持原类型不放宽：清单类配置（侧栏 widget、社交链接）的覆盖语义是整体替换，
 * 半个元素没有意义，而且保留完整类型才能让判别联合的 `type` 字段继续生效。
 */
type DeepPartial<T> = T extends readonly unknown[]
	? T
	: T extends object
		? { [K in keyof T]?: DeepPartial<T[K]> }
		: T;

// config/site.yaml
const site: DeepPartial<SiteConfig> = {
	site: "https://kuhaiyongcun.com",
	base: "/blog/",
	title: "主舰／档案室",
	subtitle: "kuhai 的个人博客。由主舰进入档案室，阅读文章与建站记录。",
	lang: "zh_CN",
	timeZone: "Asia/Shanghai",
	topAppBar: {
		contentAlign: "left",
	},
	themeColor: {
		hue: 220,
		style: "tonalSpot",
	},
	wallpaperMode: {
		defaultMode: "none",
	},
	texture: {
		enable: false,
	},
	displaySettings: {
		wallpaperMode: false,
		texture: false,
	},
	banner: {
		src: {
			desktop: [],
			mobile: [],
		},
		homeText: {
			enable: false,
			title: "主舰／档案室",
			subtitle: [
				"kuhai 的个人博客。由主舰进入档案室，阅读文章与建站记录。",
			],
			typewriter: {
				enable: false,
				speed: 100,
				loop: false,
			},
		},
		carousel: {
			enable: false,
		},
		waves: {
			enable: false,
		},
	},
	favicon: [
		{
			src: "/images/kuhai-mark.svg",
		},
	],
};

// config/profile.yaml
const profile: DeepPartial<ProfileConfig> = {
	avatar: "/images/kuhai-mark.svg",
	name: "kuhai",
	bio: "个人博客与持续生长的主舰。",
	links: [],
};

// config/announcement.yaml
const announcement: DeepPartial<AnnouncementConfig> = {
	content: "",
	link: {
		enable: false,
	},
};

// config/post-list.yaml
const postList: DeepPartial<PostListConfig> = {
	pageSize: 10,
	layout: {
		mode: "list",
		cover: "left",
		cardWidth: "regular",
	},
};

// config/comment.yaml
const comment: DeepPartial<CommentConfig> = {
	enable: false,
	provider: "none",
};

// config/context-menu.yaml
const contextMenu: DeepPartial<ContextMenuConfig> = {
	enable: false,
};

// config/sidebar.yaml
const sidebar: DeepPartial<SidebarConfig> = {
	enable: true,
	arrangement: "single",
	side: "left",
	components: [
		{
			type: "profile",
			enable: true,
			slot: "top",
		},
		{
			type: "categories",
			enable: true,
			slot: "sticky",
			collapseAfter: 5,
		},
		{
			type: "tags",
			enable: true,
			slot: "sticky",
			collapseAfter: 6,
		},
	],
};

// config/footer.yaml
const footer: DeepPartial<FooterConfig> = {
	enable: true,
};

// config/skills.yaml
const skills: DeepPartial<SkillsConfig> = {
	enable: false,
};

// config/projects.yaml
const projects: DeepPartial<ProjectsConfig> = {
	enable: false,
};

// config/timeline.yaml
const timeline: DeepPartial<TimelineConfig> = {
	enable: false,
};

// config/devices.yaml
const devices: DeepPartial<DevicesConfig> = {
	enable: false,
};

// config/games.yaml
const games: DeepPartial<GamesConfig> = {
	enable: false,
};

// config/music.yaml
const music: DeepPartial<MusicConfig> = {
	enable: false,
};

// config/anime.yaml
const anime: DeepPartial<AnimeConfig> = {
	enable: false,
};

// config/font.yaml
const font: DeepPartial<FontConfig> = {
	mode: "custom",
	fontFamilies: [
		{
			id: "outfit-body",
			family: "Outfit",
			role: "body",
			source: "local",
			variants: [
				{
					file: "src/assets/fonts/kuhai-local/outfit-latin-400-normal.woff2",
					weight: 400,
					style: "normal",
				},
				{
					file: "src/assets/fonts/kuhai-local/outfit-latin-500-normal.woff2",
					weight: 500,
					style: "normal",
				},
				{
					file: "src/assets/fonts/kuhai-local/outfit-latin-700-normal.woff2",
					weight: 700,
					style: "normal",
				},
			],
			fallback: [
				"ui-sans-serif",
				"system-ui",
				"sans-serif",
			],
			display: "swap",
			preload: false,
			licenseFile: "src/assets/fonts/kuhai-local/LICENSE-Outfit.txt",
		},
		{
			id: "yozai-cjk",
			family: "Yozai Medium",
			role: "cjk",
			source: "local",
			variants: [
				{
					file: "src/assets/fonts/Yozai-Medium.ttf",
					weight: 500,
					style: "normal",
				},
			],
			fallback: [
				"system-ui",
				"sans-serif",
			],
			display: "swap",
			preload: false,
		},
		{
			id: "jetbrains-mono",
			family: "JetBrains Mono Variable",
			role: "mono",
			source: "local",
			variants: [
				{
					file: "src/assets/fonts/kuhai-local/jetbrains-mono-latin-wght-normal.woff2",
					weight: "100 800",
					style: "normal",
				},
				{
					file: "src/assets/fonts/kuhai-local/jetbrains-mono-latin-wght-italic.woff2",
					weight: "100 800",
					style: "italic",
				},
			],
			fallback: [
				"ui-monospace",
				"SFMono-Regular",
				"Menlo",
				"Monaco",
				"Consolas",
				"monospace",
			],
			display: "swap",
			preload: false,
			licenseFile: "src/assets/fonts/kuhai-local/LICENSE-JetBrains-Mono.txt",
		},
	],
	subsetting: {
		enable: true,
		includeContent: true,
		includeI18n: true,
		includeConfig: true,
		includeCommon: true,
		allowRemoteText: false,
	},
	budget: {
		maxTotalBytes: 6291456,
		maxFamilyBytes: 4194304,
	},
};

// config/llms.yaml
const llms: DeepPartial<LlmsConfig> = {
	enable: true,
	generateFull: true,
	siteSummary: "kuhai 的个人博客。主舰是网站入口，档案室用于文章阅读与归档。",
	corePages: [
		{
			title: "档案室",
			url: "/",
			description: "文章列表",
		},
		{
			title: "归档",
			url: "/archive/",
			description: "按时间、分类和标签浏览文章",
		},
		{
			title: "关于本站",
			url: "/about/",
			description: "网站结构与阅读方式",
		},
	],
	customSections: [],
};

// config/umami.yaml
const umami: DeepPartial<UmamiConfig> = {
	enable: false,
	shareUrl: "",
	websiteId: "",
	scriptUrl: "",
};

// config/about.yaml
const about: DeepPartial<AboutConfig> = {
	enable: true,
	title: "关于本站",
	description: "主舰与档案室",
};

// config/friends.yaml
const friends: DeepPartial<FriendsConfig> = {
	enable: false,
};

// config/moments.yaml
const moments: DeepPartial<MomentsConfig> = {
	enable: false,
};

// config/albums.yaml
const albums: DeepPartial<AlbumsConfig> = {
	enable: false,
};

// config/compass.yaml
const compass: DeepPartial<CompassConfig> = {
	enable: false,
};

// config/series.yaml
const series: DeepPartial<SeriesConfig> = {
	enable: false,
};

// config/nav-bar.yaml
const navBar: NavBarConfigOverride = {
	links: [
		{
			name: "$t:flagshipReviewBack",
			url: "/",
			fullReload: true,
			icon: "material-symbols:rocket-launch-outline-rounded",
			pageKey: "flagship",
		},
		{
			preset: "Home",
			name: "$t:flagshipReviewArchive",
		},
		{
			preset: "Archive",
		},
		{
			preset: "Categories",
		},
		{
			preset: "Tags",
		},
		{
			preset: "About",
		},
	],
};

/** 领域名 -> 该领域的用户覆盖值（仅包含用户显式声明的键）。 */
export const userConfigOverrides: Readonly<Record<string, unknown>> = {
	site,
	profile,
	announcement,
	postList,
	comment,
	contextMenu,
	sidebar,
	footer,
	skills,
	projects,
	timeline,
	devices,
	games,
	music,
	anime,
	font,
	llms,
	umami,
	about,
	friends,
	moments,
	albums,
	compass,
	series,
	navBar,
};

/** 本次生成消费了内容仓中的哪些文件，用于溯源与错误提示。 */
export const userConfigSources: readonly string[] = [
	"config/site.yaml",
	"config/profile.yaml",
	"config/announcement.yaml",
	"config/post-list.yaml",
	"config/comment.yaml",
	"config/context-menu.yaml",
	"config/sidebar.yaml",
	"config/footer.yaml",
	"config/skills.yaml",
	"config/projects.yaml",
	"config/timeline.yaml",
	"config/devices.yaml",
	"config/games.yaml",
	"config/music.yaml",
	"config/anime.yaml",
	"config/font.yaml",
	"config/llms.yaml",
	"config/umami.yaml",
	"config/about.yaml",
	"config/friends.yaml",
	"config/moments.yaml",
	"config/albums.yaml",
	"config/compass.yaml",
	"config/series.yaml",
	"config/nav-bar.yaml",
];
