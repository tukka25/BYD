import { Dashboards } from "@/components/dashboards";
import { DataPipeline } from "@/components/data-pipeline";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/how-it-works";
import { Problem } from "@/components/problem";
import { FineTuning } from "@/components/results";
import { RunIt } from "@/components/run-it";
import { Training } from "@/components/training";

/* The story in the owner's order (revision 4): the hook, the three dashboards,
   the problem, the fine-tune and its results, then how it was done in three
   numbered parts, and how to run it. */
export default function Home() {
  return (
    <>
      <main>
        <Hero />
        <Dashboards />
        <Problem />
        <FineTuning />
        <DataPipeline />
        <Training />
        <HowItWorks />
        <RunIt />
      </main>
      <Footer />
    </>
  );
}
