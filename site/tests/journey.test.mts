import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

type Milestone = { date: string; commit: string; subject: string; title: string; text: string };
const journey: Milestone[] = JSON.parse(readFileSync(new URL("../data/journey.json", import.meta.url), "utf8"));

/* If part 2 rewrites the history, these hashes change. Find each milestone's
   new hash by its subject: git log --format='%h %ad %s' --date=short */
for (const milestone of journey) {
  test(`${milestone.date} "${milestone.title}" is commit ${milestone.commit}`, () => {
    const shown = execFileSync("git", ["show", "-s", "--format=%ad%x09%s", "--date=short", milestone.commit], {
      encoding: "utf8",
    }).trim();
    assert.equal(shown, `${milestone.date}\t${milestone.subject}`);
  });
}

test("the milestones run in date order", () => {
  const dates = journey.map((milestone) => milestone.date);
  assert.deepEqual(dates, [...dates].sort());
});
