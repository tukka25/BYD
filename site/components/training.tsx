import loss from "@/data/loss.json";
import { LossChart } from "@/components/loss-chart";
import { stat } from "@/components/numbers";
import { Lede, Section } from "@/components/section";

export function Training() {
  const v1Names = loss.v1.points.map((_, i) => (i === 0 ? "before training" : `evaluation ${i}`));
  const v2Names = loss.v2.steps.map((step) => `step ${step.toLocaleString("en-US")}`);
  return (
    <Section id="training" kicker="Training" title="LoRA on one rented A100">
      <div className="grid gap-8 lg:grid-cols-[1fr_1.15fr] lg:gap-12">
        <div className="space-y-4">
          <Lede>
            LoRA adapters on Qwen3.5-9B, trained on one A100 80 GB on Runpod at {stat("gpu_rate")} an hour.
          </Lede>
          <Lede>
            lora-v1: {stat("v1_pod_time")} of pod time, validation loss {stat("v1_loss_start")} →{" "}
            {stat("v1_loss_end")}, {stat("v1_cloud_cost", 2)} of cloud time.
          </Lede>
          <Lede>
            lora-v2: {stat("v2_epochs")} epochs, {stat("v2_steps")} steps, {stat("v2_hours")} h, validation loss{" "}
            {stat("v2_loss_start")} → {stat("v2_loss_end")}, {stat("v2_cloud_cost")} of cloud time. The two runs score
            against different validation sets, so their curves do not compare.
          </Lede>
          <Lede>Each adapter is converted from PEFT to MLX and served at 4-bit on a Mac with mlx_lm, beside the app.</Lede>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <LossChart
            label={loss.v1.label}
            points={loss.v1.points}
            names={v1Names}
            caption={`before training, then ${loss.v1.points.length - 1} evaluations`}
          />
          <LossChart
            label={loss.v2.label}
            points={loss.v2.points}
            names={v2Names}
            caption={`${v2Names[0]} to ${v2Names[v2Names.length - 1]}`}
          />
        </div>
      </div>
    </Section>
  );
}
