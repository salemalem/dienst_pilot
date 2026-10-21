import { Platform } from "react-native";

const memory = new Map<string, string>();

/**
 * Small key-value store for the demo token, persona and language. Web uses localStorage; native
 * keeps it in memory (a demo sign-in is one tap, so no native storage dependency is added).
 */
export const storage = {
  get(key: string): string | null {
    if (Platform.OS === "web") {
      try {
        return window.localStorage.getItem(key);
      } catch {
        return memory.get(key) ?? null;
      }
    }
    return memory.get(key) ?? null;
  },
  set(key: string, value: string | null): void {
    if (Platform.OS === "web") {
      try {
        if (value === null) window.localStorage.removeItem(key);
        else window.localStorage.setItem(key, value);
        return;
      } catch {
        // Storage blocked: fall through to memory.
      }
    }
    if (value === null) memory.delete(key);
    else memory.set(key, value);
  },
};
