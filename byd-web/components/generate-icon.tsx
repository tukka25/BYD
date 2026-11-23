import type { SVGProps } from "react";

/* Generate dashboard: a chart in a frame, with the model's spark at the
   frame's open corner. Redrawn from the 24px icon the user supplied, as lucide
   draws (a 24-unit box, a currentColor stroke, round caps and joins), so it
   takes the app's one stroke weight like every other icon instead of arriving
   as a bitmap with a weight of its own. */
export function GenerateDashboardIcon({
  size = 24,
  strokeWidth = 2.25,
  ...props
}: { size?: number; strokeWidth?: number } & Omit<SVGProps<SVGSVGElement>, "width" | "height">) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" />
      <path d="m4 14 3-2 2.5 2.5L13 11" />
      <path d="M17.5 1.75Q18.1 5.4 21.75 6Q18.1 6.6 17.5 10.25Q16.9 6.6 13.25 6Q16.9 5.4 17.5 1.75Z" />
    </svg>
  );
}
