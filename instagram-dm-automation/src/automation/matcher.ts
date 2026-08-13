export type MatchType = "CONTAINS" | "EXACT" | "STARTS_WITH";

export function matchesKeyword(text: string, keyword: string, matchType: string): boolean {
  const haystack = text.trim().toLowerCase();
  const needle = keyword.trim().toLowerCase();
  if (!needle) return false;

  switch (matchType) {
    case "EXACT":
      return haystack === needle;
    case "STARTS_WITH":
      return haystack.startsWith(needle);
    case "CONTAINS":
    default:
      return haystack.includes(needle);
  }
}
