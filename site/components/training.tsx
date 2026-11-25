import { stat } from "@/components/numbers";
import { Lede, Section } from "@/components/section";

export function Training() {
  return (
    <Section id="training" kicker="Training" title="LoRA on one rented A100">
      <div className="max-w-3xl space-y-4">
        <Lede>LoRA adapters on Qwen3.5-9B, trained on one A100 80 GB on Runpod.</Lede>
        <Lede>
          lora-v1: {stat("v1_pod_time")} of pod time, validation loss {stat("v1_loss_start")} → {stat("v1_loss_end")}.
        </Lede>
        <Lede>
          lora-v2: {stat("v2_epochs")} epochs, {stat("v2_steps")} steps, {stat("v2_hours")} h, validation loss{" "}
          {stat("v2_loss_start")} → {stat("v2_loss_end")}. The two runs score against different validation sets, so
          their curves do not compare.
        </Lede>
        <Lede>Each adapter is converted from PEFT to MLX and served at 4-bit on a Mac with mlx_lm, beside the app.</Lede>
      </div>
    </Section>
  );
}
