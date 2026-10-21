/**
 * Where the API is. Native reaches the host's backend at localhost on the iOS simulator
 * (`10.0.2.2` on the Android emulator: set EXPO_PUBLIC_API_URL). Expo web calls the same URL
 * from the browser, which the API allows in DEMO_MODE for the dev origins (ADR-011).
 */
export const API_URL: string = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

/** The demo personas of the staff app (UI_SPEC §1). Kaya is the default. */
export const PERSONAS = ["kaya", "weber", "alvarez", "mehta", "lorenz"] as const;
export type PersonaKey = (typeof PERSONAS)[number];
