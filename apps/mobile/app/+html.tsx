import { ScrollViewStyleReset } from "expo-router/html";
import type { ReactNode } from "react";

/** The web document: full-height root for the app and a mobile viewport. */
export default function Root({ children }: { children: ReactNode }): ReactNode {
  return (
    <html lang="de">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
        <title>DienstPilot</title>
        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  );
}
