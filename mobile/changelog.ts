// The app's "What's New" data. The array itself lives in changelog.data.json so
// the daily OTA workflow (.github/workflows/mobile-ota.yml) can safely prepend a
// new entry (from model metrics + notable commits) without parsing TypeScript,
// then publish an EAS Update — installed apps pick up the improvement AND its
// changelog live, no app-store release.

import data from "./changelog.data.json";

export type ChangeEntry = {
  id: string;      // stable unique id (date or build)
  date: string;    // YYYY-MM-DD
  title: string;   // one-line headline
  items: string[]; // what changed / improved
};

export const CHANGELOG: ChangeEntry[] = data as ChangeEntry[];

// Most-recent entry id; the app shows "What's New" once when this differs from
// the last id the user acknowledged.
export const CHANGELOG_VERSION = CHANGELOG[0]?.id ?? "0";
