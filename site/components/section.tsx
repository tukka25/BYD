import type { ReactNode } from "react";

/* The page's type scale for reading at length. Body text is 17px, 18px from
   `sm`, in --ink at a 1.7 line height, held to about 70 characters a line;
   captions are 14px in --body, and no story text is smaller. */
export const BODY = "text-[17px] leading-[1.7] text-ink text-pretty sm:text-[18px]";
export const MEASURE = "max-w-[36.5rem]";
export const CAPTION = "text-[14px] leading-[1.6] text-body";

/* One part of the story: a title, then its text and one figure, table or list.
   No eyebrow above the title: byd-web/DESIGN.md bans them. */
export function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="mx-auto max-w-6xl px-4 py-14 sm:px-8 sm:py-20">
      <h2 id={`${id}-title`} className="max-w-3xl font-display text-[28px] font-bold leading-tight sm:text-[36px]">
        {title}
      </h2>
      <div className="mt-6 sm:mt-8">{children}</div>
    </section>
  );
}

/* A paragraph of the story. */
export function Lede({ children }: { children: ReactNode }) {
  return <p className={`${MEASURE} ${BODY}`}>{children}</p>;
}

/* Code named in a sentence, sized to sit in the line and never split at a
   hyphen ("make serve-model" stays whole). */
export function Code({ children }: { children: ReactNode }) {
  return <code className="whitespace-nowrap rounded-[5px] bg-sunken px-1 py-px font-mono text-[0.88em]">{children}</code>;
}

/* A name that must not split at its hyphen, such as lora-v2 or Qwen3.5-9B. */
export function Name({ children }: { children: ReactNode }) {
  return <span className="whitespace-nowrap">{children}</span>;
}

/* Text whose dates stay whole: "2021-04-20" never breaks at a hyphen. */
export function KeepDates({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(\d{4}-\d{2}-\d{2})/)
        .map((piece, index) => (index % 2 ? <Name key={index}>{piece}</Name> : piece))}
    </>
  );
}
