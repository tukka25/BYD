import type { ReactNode } from "react";

/* One part of the story: a short title, a few technical sentences, then one
   figure, table or diagram. */
export function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-6xl px-4 py-14 sm:px-8 sm:py-16">
      <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-pine">{kicker}</p>
      <h2 className="mt-3 max-w-3xl font-display text-[28px] font-bold leading-tight sm:text-[34px]">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export function Lede({ children }: { children: ReactNode }) {
  return <p className="max-w-3xl text-[16px] leading-relaxed">{children}</p>;
}
