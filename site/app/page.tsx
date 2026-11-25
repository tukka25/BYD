import { Dashboards } from "@/components/dashboards";
import { DataPipeline } from "@/components/data-pipeline";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/how-it-works";
import { Problem } from "@/components/problem";
import { Results } from "@/components/results";
import { RunIt } from "@/components/run-it";
import { Training } from "@/components/training";

export default function Home() {
  return (
    <>
      <main>
        <Hero />
        <Dashboards />
        <Problem />
        <DataPipeline />
        <Training />
        <HowItWorks />
        <Results />
        <RunIt />
      </main>
      <Footer />
    </>
  );
}
