/* Where the page links. Part 2 (open source) renames the repository: change
   REPO_URL then, and every link follows. Import-free. */
export const REPO_URL = "https://github.com/tukka25/BYD";
/* The owner's LinkedIn profile. Empty until it is known: the footer draws the
   link only when this is set, and never a guessed address. */
export const LINKEDIN_URL = "https://www.linkedin.com/in/abdalrahman-tukka/";
export const AUTHOR = { handle: "@tukka25", url: "https://github.com/tukka25" };

export const fileUrl = (path: string): string => `${REPO_URL}/blob/main/${path}`;
export const commitUrl = (hash: string): string => `${REPO_URL}/commit/${hash}`;

/* The card and page title of each committed dashboard, by file name. */
export const DASHBOARD_TITLES: Record<string, string> = {
  airbnb: "Airbnb Dashboard",
  shop: "Shop Dashboard",
  netflix: "Netflix Dashboard",
};
