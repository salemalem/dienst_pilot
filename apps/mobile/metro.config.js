// Expo's default config detects the pnpm workspace; we only add the woff2 font files the
// design tokens ship (loaded on web).
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);
if (!config.resolver.assetExts.includes("woff2")) config.resolver.assetExts.push("woff2");

module.exports = config;
