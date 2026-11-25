/* Plotly, imported once, when the first chart comes near the screen: it is the
   largest thing on the page, and a visitor reads the top first. */
export type PlotlyApi = {
  react: (el: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>;
  Plots: { resize: (el: HTMLElement) => void };
  purge: (el: HTMLElement) => void;
};

let loading: Promise<PlotlyApi> | null = null;

export function loadPlotly(): Promise<PlotlyApi> {
  loading ??= import("plotly.js-dist-min").then((mod) => (mod.default ?? mod) as unknown as PlotlyApi);
  return loading;
}
