import { Redirect } from "expo-router";
import type { ReactNode } from "react";

import { useSession } from "../src/lib/session";

/** The entry: today when signed in, the sign-in screen (M1) otherwise. */
export default function Index(): ReactNode {
  const { me, ready } = useSession();
  if (!ready) return null;
  return <Redirect href={me ? "/today" : "/sign-in"} />;
}
