import { startStack } from "../e2e/stack.ts";
import { API_PORT } from "./src/env.ts";

/** A clean seed (seeding --reset), the demo clock back at 06:00, and the API with its worker. */
export default async function globalSetup(): Promise<() => void> {
  return startStack(API_PORT);
}
