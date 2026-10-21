import { startStack } from "../../../scripts/e2e/stack.ts";
import { API_PORT } from "../playwright.config.ts";

/** Seeds the e2e database and starts the API and the worker (see scripts/e2e/stack.ts). */
export default async function globalSetup(): Promise<() => void> {
  return startStack(API_PORT);
}
