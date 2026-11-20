import { redirect } from "next/navigation";

// Superseded by the reports/canvas routes. Kept as a redirect so an old link or
// bookmark still lands somewhere sensible.
export default function Page() {
  redirect("/");
}
