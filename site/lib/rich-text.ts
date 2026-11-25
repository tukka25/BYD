/* Formatting for note blocks.

   A note is authored in a contenteditable, so what comes back is whatever
   markup the browser decided to produce — and what goes back on screen is
   rendered as HTML. Everything therefore passes through `sanitizeRichText`
   on the way in AND on the way out: the stored text is still the user's own,
   but a note written on one machine should not be able to run anything on
   another, and a block of stored text is exactly the kind of thing that gets
   copied around.

   The sanitiser is a tokeniser over an allowlist rather than a DOM pass, so it
   gives the same answer during server rendering as it does in the browser —
   `DOMParser` exists only in one of those. It keeps no attribute at all except
   a validated `href`, so an attribute-borne handler (`onerror=`) has nothing
   to ride in on: the tag carrying it is not in the list and is dropped whole.
*/

const ALLOWED = new Set([
  "p",
  "br",
  "strong",
  "em",
  "u",
  "s",
  "h2",
  "h3",
  "ul",
  "ol",
  "li",
  "a",
  "code",
  "blockquote",
]);

/* What a browser's execCommand actually emits, mapped onto the list above. */
const RENAME: Record<string, string> = {
  b: "strong",
  i: "em",
  div: "p",
  strike: "s",
  del: "s",
  h1: "h2",
  h4: "h3",
  h5: "h3",
  h6: "h3",
};

const TAG = /<\/?[a-zA-Z][^>]*>/g;
const PARSE_TAG = /^<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>$/;
const HREF = /href\s*=\s*(?:"([^"]*)"|'([^']*)')/i;
const SAFE_HREF = /^(https?:\/\/|mailto:)[^\s"'<>]+$/i;

/* `&` is left alone: the editor already serialises a typed ampersand as
   `&amp;`, so escaping here would double it. `<` and `>` in text are escaped
   so a stray bracket cannot start a tag after the pass. */
function escapeText(text: string): string {
  return text.replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function sanitizeRichText(input: string | null | undefined): string {
  if (!input) return "";

  let out = "";
  let last = 0;
  // Only `a` can be allowed as a tag and still dropped (a rejected href), so
  // its closing tag has to be matched against one we actually emitted —
  // otherwise a stray `</a>` closes a surrounding link early.
  let openAnchors = 0;

  // Drop script/style outright, content and all, before anything else sees it.
  const source = input.replace(/<(script|style)\b[\s\S]*?<\/\1\s*>/gi, "");

  for (const match of source.matchAll(TAG)) {
    const token = match[0];
    const at = match.index ?? 0;
    out += escapeText(source.slice(last, at));
    last = at + token.length;

    const parsed = PARSE_TAG.exec(token);
    if (!parsed) continue;

    const closing = parsed[1] === "/";
    const raw = parsed[2].toLowerCase();
    const name = RENAME[raw] ?? raw;
    if (!ALLOWED.has(name)) continue;

    if (closing) {
      if (name === "a") {
        if (openAnchors === 0) continue;
        openAnchors -= 1;
      }
      out += `</${name}>`;
      continue;
    }

    if (name === "a") {
      const href = HREF.exec(parsed[3]);
      const url = (href?.[1] ?? href?.[2] ?? "").trim();
      // A link with no usable target keeps its text but stops being a link.
      if (!SAFE_HREF.test(url)) continue;
      openAnchors += 1;
      out += `<a href="${url.replace(/"/g, "&quot;")}" rel="noreferrer noopener" target="_blank">`;
      continue;
    }

    out += `<${name}>`;
  }

  out += escapeText(source.slice(last));
  return out;
}

/** True when a stored body is formatted markup rather than legacy plain text. */
export function isRichText(value: string | null | undefined): boolean {
  if (!value) return false;
  return /<(p|br|strong|em|u|s|h2|h3|ul|ol|li|a|code|blockquote)\b[^>]*>/i.test(value);
}

/** Notes written before formatting existed are plain text with newlines. */
export function plainToHtml(value: string | null | undefined): string {
  if (!value?.trim()) return "";
  return value
    .split(/\n/)
    .map((line) => (line.trim() ? `<p>${escapeText(line)}</p>` : "<p><br></p>"))
    .join("");
}

/** The body as HTML, whichever of the two forms it was stored in. */
export function toHtml(value: string | null | undefined): string {
  return isRichText(value) ? sanitizeRichText(value) : plainToHtml(value);
}

/** Whether a note has any text in it, ignoring the markup around it. */
export function isEmptyRichText(value: string | null | undefined): boolean {
  if (!value) return true;
  return !value
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .trim();
}
