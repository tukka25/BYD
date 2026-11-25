import type { SVGProps } from "react";

type IconProps = Omit<SVGProps<SVGSVGElement>, "width" | "height"> & { size?: number };

/* The LinkedIn "in" mark, in the same 16px box and fill as GitHubMark. */
export function LinkedInMark({ size = 16, ...props }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M0 1.15C0 .52.52 0 1.17 0h13.66C15.48 0 16 .52 16 1.15v13.7c0 .63-.52 1.15-1.17 1.15H1.17C.52 16 0 15.48 0 14.85V1.15zM4.94 13.4V6.17H2.54v7.23h2.4zM3.74 5.18c.84 0 1.36-.55 1.36-1.25-.02-.71-.52-1.25-1.34-1.25-.83 0-1.37.54-1.37 1.25 0 .7.52 1.25 1.33 1.25h.02zM13.45 13.4V9.25c0-2.22-1.18-3.25-2.76-3.25-1.27 0-1.84.7-2.16 1.19V6.17h-2.4c.03.68 0 7.23 0 7.23h2.4V9.36c0-.22.02-.43.08-.59.17-.43.57-.88 1.23-.88.87 0 1.21.66 1.21 1.63v3.88h2.4z" />
    </svg>
  );
}

/* A repository: the book outline, as GitHub draws it for "repo". */
export function RepoMark({ size = 16, ...props }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75c.41 0 .75.34.75.75v12.5c0 .41-.34.75-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.71 1.7.75.75 0 0 1-1.07 1.05A2.5 2.5 0 0 1 2 11.5v-9zm10.5-1h-8a1 1 0 0 0-1 1v6.71A2.5 2.5 0 0 1 4.5 9h8V1.5zM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.09a.25.25 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2v-3.25z" />
    </svg>
  );
}
