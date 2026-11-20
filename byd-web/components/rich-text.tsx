"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bold,
  Heading2,
  Italic,
  List,
  ListOrdered,
  RemoveFormatting,
  Underline,
} from "lucide-react";
import { isEmptyRichText, sanitizeRichText, toHtml } from "@/lib/rich-text";

/* A note you can format. The editor is a contenteditable rather than a
   textarea, so bold text looks bold while you are writing it instead of
   looking like `**bold**`.

   It is deliberately UNCONTROLLED: React owns the value at mount and at blur,
   and the browser owns it in between. Writing the value back into the DOM on
   every keystroke is what makes a contenteditable put the caret back at the
   start of the line. */

type Command = "bold" | "italic" | "underline" | "insertUnorderedList" | "insertOrderedList";

function exec(command: string, value?: string) {
  // execCommand is deprecated and still the only cross-browser way to do this
  // without shipping an editor framework for one block type.
  document.execCommand(command, false, value);
}

function ToolButton({
  label,
  active,
  onPress,
  children,
}: {
  label: string;
  active?: boolean;
  onPress: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      // Keeps the caret where it was: without this the button takes focus and
      // the command has no selection to act on.
      onMouseDown={(event) => event.preventDefault()}
      onClick={onPress}
      className={[
        "inline-grid size-7 place-items-center rounded-[8px] transition-colors duration-150",
        active ? "bg-pine-wash text-pine" : "text-muted hover:bg-sunken hover:text-ink",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function RichTextEditor({
  value,
  onCommit,
  placeholder = "Write a note, a caption, or what this section shows…",
}: {
  value: string | null | undefined;
  onCommit: (html: string) => void;
  placeholder?: string;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const seeded = useRef(false);
  const [empty, setEmpty] = useState(() => isEmptyRichText(value));
  const [active, setActive] = useState<Record<string, boolean>>({});

  // Seeded once. See the note above about why this is not a controlled input.
  useEffect(() => {
    const node = host.current;
    if (!node || seeded.current) return;
    seeded.current = true;
    node.innerHTML = toHtml(value);
    setEmpty(isEmptyRichText(node.innerHTML));
  }, [value]);

  const refreshActive = useCallback(() => {
    const node = host.current;
    if (!node || !node.contains(document.activeElement)) return;
    setActive({
      bold: document.queryCommandState("bold"),
      italic: document.queryCommandState("italic"),
      underline: document.queryCommandState("underline"),
      insertUnorderedList: document.queryCommandState("insertUnorderedList"),
      insertOrderedList: document.queryCommandState("insertOrderedList"),
    });
  }, []);

  useEffect(() => {
    document.addEventListener("selectionchange", refreshActive);
    return () => document.removeEventListener("selectionchange", refreshActive);
  }, [refreshActive]);

  function run(command: Command) {
    host.current?.focus();
    exec(command);
    refreshActive();
    setEmpty(isEmptyRichText(host.current?.innerHTML));
  }

  function heading() {
    host.current?.focus();
    const inHeading = document.queryCommandValue("formatBlock").toLowerCase().includes("h2");
    exec("formatBlock", inHeading ? "<p>" : "<h2>");
    refreshActive();
  }

  function clearFormatting() {
    host.current?.focus();
    exec("removeFormat");
    exec("formatBlock", "<p>");
    refreshActive();
  }

  function commit() {
    const node = host.current;
    if (!node) return;
    const clean = sanitizeRichText(node.innerHTML);
    // Written back so what is stored and what is on screen cannot drift.
    node.innerHTML = clean;
    onCommit(isEmptyRichText(clean) ? "" : clean);
  }

  return (
    <div className="flex size-full flex-col overflow-hidden rounded-[var(--r-card)] bg-sunken">
      <div className="flex flex-wrap items-center gap-0.5 px-2 pt-1.5">
        <ToolButton label="Bold" active={active.bold} onPress={() => run("bold")}>
          <Bold size={14} strokeWidth={2.25} />
        </ToolButton>
        <ToolButton label="Italic" active={active.italic} onPress={() => run("italic")}>
          <Italic size={14} strokeWidth={2.25} />
        </ToolButton>
        <ToolButton label="Underline" active={active.underline} onPress={() => run("underline")}>
          <Underline size={14} strokeWidth={2.25} />
        </ToolButton>
        <span className="mx-1 h-4 w-px bg-hairline-strong" aria-hidden />
        <ToolButton label="Heading" onPress={heading}>
          <Heading2 size={14} strokeWidth={2.25} />
        </ToolButton>
        <ToolButton
          label="Bulleted list"
          active={active.insertUnorderedList}
          onPress={() => run("insertUnorderedList")}
        >
          <List size={14} strokeWidth={2.25} />
        </ToolButton>
        <ToolButton
          label="Numbered list"
          active={active.insertOrderedList}
          onPress={() => run("insertOrderedList")}
        >
          <ListOrdered size={14} strokeWidth={2.25} />
        </ToolButton>
        <span className="mx-1 h-4 w-px bg-hairline-strong" aria-hidden />
        <ToolButton label="Clear formatting" onPress={clearFormatting}>
          <RemoveFormatting size={14} strokeWidth={2.25} />
        </ToolButton>
      </div>

      <div
        ref={host}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label="Note text"
        data-placeholder={placeholder}
        data-empty={empty || undefined}
        onInput={() => setEmpty(isEmptyRichText(host.current?.innerHTML))}
        onBlur={commit}
        onKeyDown={(event) => event.stopPropagation()}
        onPaste={(event) => {
          // Paste keeps bold and lists but nothing else: the clipboard is the
          // one place a note can pick up markup nobody in this app wrote.
          event.preventDefault();
          const html = event.clipboardData.getData("text/html");
          const text = event.clipboardData.getData("text/plain");
          if (html) exec("insertHTML", sanitizeRichText(html));
          else exec("insertText", text);
          setEmpty(isEmptyRichText(host.current?.innerHTML));
        }}
        className="rich-text min-h-0 flex-1 overflow-auto px-4 pb-3 pt-2 text-sm leading-relaxed text-body focus:outline-none"
      />
    </div>
  );
}

/** The same note, rendered rather than edited. */
export function RichText({ value }: { value: string | null | undefined }) {
  if (isEmptyRichText(value)) {
    return <span className="text-muted">Empty note</span>;
  }
  return (
    <div
      className="rich-text size-full overflow-auto px-2 py-1 text-sm leading-relaxed text-body"
      // Sanitised here as well as at commit: a body can reach this component
      // from the database, which is not the same trust boundary as this tab.
      dangerouslySetInnerHTML={{ __html: toHtml(value) }}
    />
  );
}
