import { Fragment } from 'react';
import type { ReactNode } from 'react';

/**
 * Small, dependency-free Markdown renderer for chat answers: headings, paragraphs, lists,
 * tables, fenced code, blockquotes, rules, **bold**, *italic*, `code`, [links](https://…)
 * and [n] citation chips. Raw HTML is never interpreted (everything goes through React nodes)
 * and only http(s) links are rendered as links.
 */

export type CiteHandler = (n: number) => void;

const INLINE_RE =
  /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\)|\[\d+(?:\s*,\s*\d+)*\]|(?<![*\w])\*[^*\s][^*\n]*\*(?![*\w]))/g;
const CITE_RE = /^\[(\d+(?:\s*,\s*\d+)*)\]$/;
const LINK_RE = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/;

export function renderInline(text: string, onCite: CiteHandler, sourceWord: string, keyPrefix = ''): ReactNode[] {
  return text
    .split(INLINE_RE)
    .filter(Boolean)
    .map((part, i) => {
      const key = `${keyPrefix}${i}`;
      if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
        return <code key={key}>{part.slice(1, -1)}</code>;
      }
      if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
        return <strong key={key}>{renderInline(part.slice(2, -2), onCite, sourceWord, `${key}.`)}</strong>;
      }
      const link = part.match(LINK_RE);
      if (link) {
        return (
          <a key={key} href={link[2]} target="_blank" rel="noopener noreferrer">
            {link[1]}
          </a>
        );
      }
      const cite = part.match(CITE_RE);
      if (cite) {
        return (
          <span className="cites" key={key}>
            {cite[1].split(',').map((s) => {
              const n = Number(s.trim());
              return (
                <button key={n} type="button" className="cite" aria-label={`${sourceWord} ${n}`} onClick={() => onCite(n)}>
                  {n}
                </button>
              );
            })}
          </span>
        );
      }
      if (part.length > 2 && part.startsWith('*') && part.endsWith('*') && !part.startsWith('**')) {
        return <em key={key}>{renderInline(part.slice(1, -1), onCite, sourceWord, `${key}.`)}</em>;
      }
      return part;
    });
}

const FENCE_RE = /^\s*```(\w*)\s*$/;
const HEADING_RE = /^(#{1,4})\s+(.*)$/;
const UL_RE = /^\s*[-*•]\s+/;
const OL_RE = /^\s*\d+[.)]\s+/;
const QUOTE_RE = /^\s*>\s?/;
const HR_RE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const TABLE_SEP_RE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

const splitRow = (line: string): string[] =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());

const isTableStart = (lines: string[], i: number): boolean =>
  lines[i].includes('|') && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1]) && lines[i + 1].includes('-');

const startsBlock = (lines: string[], i: number): boolean =>
  FENCE_RE.test(lines[i]) ||
  HEADING_RE.test(lines[i]) ||
  UL_RE.test(lines[i]) ||
  OL_RE.test(lines[i]) ||
  QUOTE_RE.test(lines[i]) ||
  HR_RE.test(lines[i]) ||
  isTableStart(lines, i);

export function renderMarkdown(content: string, onCite: CiteHandler, sourceWord: string): ReactNode[] {
  const inline = (s: string, k: string) => renderInline(s, onCite, sourceWord, `${k}-`);
  const lines = content.replace(/\r\n?/g, '\n').trim().split('\n');
  const out: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;

    if (!line.trim()) {
      i++;
      continue;
    }

    const fence = line.match(FENCE_RE);
    if (fence) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE_RE.test(lines[i])) code.push(lines[i++]);
      i++; // closing fence (or end of a still-streaming block)
      out.push(
        <pre key={key}>
          <code>{code.join('\n')}</code>
        </pre>,
      );
      continue;
    }

    if (HR_RE.test(line)) {
      out.push(<hr key={key} />);
      i++;
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) {
      out.push(<h4 key={key}>{inline(heading[2], key)}</h4>);
      i++;
      continue;
    }

    if (isTableStart(lines, i)) {
      const head = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(splitRow(lines[i++]));
      out.push(
        <div className="table-wrap" key={key}>
          <table>
            <thead>
              <tr>
                {head.map((c, ci) => (
                  <th key={ci}>{inline(c, `${key}h${ci}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {head.map((_, ci) => (
                    <td key={ci}>{inline(r[ci] ?? '', `${key}r${ri}c${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (QUOTE_RE.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && QUOTE_RE.test(lines[i])) quote.push(lines[i++].replace(QUOTE_RE, ''));
      out.push(<blockquote key={key}>{renderMarkdown(quote.join('\n'), onCite, sourceWord)}</blockquote>);
      continue;
    }

    if (UL_RE.test(line) || OL_RE.test(line)) {
      const ordered = OL_RE.test(line);
      const re = ordered ? OL_RE : UL_RE;
      const items: string[] = [];
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ''));
      const li = items.map((it, ii) => <li key={ii}>{inline(it, `${key}i${ii}`)}</li>);
      out.push(ordered ? <ol key={key}>{li}</ol> : <ul key={key}>{li}</ul>);
      continue;
    }

    const para: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) para.push(lines[i++]);
    out.push(
      <p key={key}>
        {para.map((l, li) => (
          <Fragment key={li}>
            {li > 0 && <br />}
            {inline(l, `${key}l${li}`)}
          </Fragment>
        ))}
      </p>,
    );
  }
  return out;
}
