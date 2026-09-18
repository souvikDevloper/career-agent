/**
 * A small markdown renderer for agent replies.
 *
 * The agent's system prompt asks it for short paragraphs and up to four bullet
 * points, and it obliges - but the chat rendered the raw string, so every reply
 * arrived as one run-on line with literal "- " and "**" in it. This renders the
 * subset the agent actually emits.
 *
 * It returns React nodes rather than an HTML string, so there is no
 * dangerouslySetInnerHTML anywhere near model output and no escaping to get
 * wrong. Links are restricted to http/https and carry noopener, because a URL
 * in a reply came from a job posting, which is untrusted data.
 */
import type { ReactNode } from "react";

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*|\bhttps?:\/\/[^\s<>()]+[^\s<>().,;:!?])/g;

function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith("**")) out.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) out.push(<code key={key}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("*")) out.push(<em key={key}>{token.slice(1, -1)}</em>);
    else out.push(
      <a key={key} href={token} target="_blank" rel="noopener noreferrer nofollow">{token}</a>,
    );
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "h"; level: number; text: string };

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of source.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];

    if (!line.trim()) {
      if (last?.kind === "p") blocks.push({ kind: "p", lines: [] }); // force a new paragraph
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "h", level: heading[1].length, text: heading[2] });
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    if (bullet) {
      if (last?.kind === "ul") last.items.push(bullet[1]);
      else blocks.push({ kind: "ul", items: [bullet[1]] });
      continue;
    }
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      if (last?.kind === "ol") last.items.push(numbered[1]);
      else blocks.push({ kind: "ol", items: [numbered[1]] });
      continue;
    }
    if (last?.kind === "p") last.lines.push(line);
    else blocks.push({ kind: "p", lines: [line] });
  }
  return blocks.filter((b) => (b.kind === "p" ? b.lines.length > 0 : true));
}

export function Markdown({ text }: { text: string }) {
  const blocks = parse(text);
  if (blocks.length === 0) return null;
  return (
    <div className="md">
      {blocks.map((block, i) => {
        if (block.kind === "h") {
          const Tag = (["h3", "h4", "h5"][block.level - 1] || "h5") as "h3" | "h4" | "h5";
          return <Tag key={i}>{inline(block.text, `h${i}`)}</Tag>;
        }
        if (block.kind === "p") {
          return (
            <p key={i}>
              {block.lines.map((line, j) => (
                <span key={j}>
                  {j > 0 && <br />}
                  {inline(line, `${i}-${j}`)}
                </span>
              ))}
            </p>
          );
        }
        const items = block.items.map((item, j) => <li key={j}>{inline(item, `${i}-${j}`)}</li>);
        return block.kind === "ul" ? <ul key={i}>{items}</ul> : <ol key={i}>{items}</ol>;
      })}
    </div>
  );
}
