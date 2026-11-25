/* Where the page links. Part 2 (open source) renames the repository: change
   REPO_URL then, and every link follows. Import-free. */
export const REPO_URL = "https://github.com/tukka25/BYD";
/* The owner's LinkedIn profile. The footer draws the link only when this is
   set (empty hides it), and never a guessed address. */
export const LINKEDIN_URL = "https://www.linkedin.com/in/abdalrahman-tukka/";
export const AUTHOR = { handle: "@tukka25", url: "https://github.com/tukka25" };

export const fileUrl = (path: string): string => `${REPO_URL}/blob/main/${path}`;

/* The card and page title of each committed dashboard, by file name. */
export const DASHBOARD_TITLES: Record<string, string> = {
  airbnb: "Airbnb Dashboard",
  shop: "Shop Dashboard",
  netflix: "Netflix Dashboard",
};
