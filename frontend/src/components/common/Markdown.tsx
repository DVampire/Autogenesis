import { isValidElement, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';

import bashLanguage from 'highlight.js/lib/languages/bash';
import cssLanguage from 'highlight.js/lib/languages/css';
import javascriptLanguage from 'highlight.js/lib/languages/javascript';
import jsonLanguage from 'highlight.js/lib/languages/json';
import markdownLanguage from 'highlight.js/lib/languages/markdown';
import pythonLanguage from 'highlight.js/lib/languages/python';
import typescriptLanguage from 'highlight.js/lib/languages/typescript';
import xmlLanguage from 'highlight.js/lib/languages/xml';
import yamlLanguage from 'highlight.js/lib/languages/yaml';

// Shared rather than living in App.tsx, because the Science view renders agent
// replies too and importing them from App would have a lazily-loaded view pull
// the whole application back in.

const HIGHLIGHT_LANGUAGES = {
  bash: bashLanguage,
  css: cssLanguage,
  javascript: javascriptLanguage,
  json: jsonLanguage,
  markdown: markdownLanguage,
  python: pythonLanguage,
  typescript: typescriptLanguage,
  xml: xmlLanguage,
  yaml: yamlLanguage,
};

export const MARKDOWN_REHYPE_PLUGINS: Parameters<typeof ReactMarkdown>[0]['rehypePlugins'] = [
  [rehypeHighlight, {
    languages: HIGHLIGHT_LANGUAGES,
    aliases: {
      bash: ['sh', 'shell', 'zsh'], javascript: ['js', 'jsx'], markdown: ['md'],
      python: ['py'], typescript: ['ts', 'tsx'], xml: ['html', 'svg'], yaml: ['yml'],
    },
    detect: false,
  }],
];

export function MessageMarkdown({ content }: { content: string }) {
  return <div className="message-markdown"><ReactMarkdown
    remarkPlugins={[remarkGfm]}
    rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
    components={{
      pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
      a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
    }}
  >{content}</ReactMarkdown></div>;
}

export function CodeBlock({ children }: { children?: ReactNode }) {
  const child = Array.isArray(children) ? children[0] : children;
  const className = isValidElement<{ className?: string }>(child) ? child.props.className ?? '' : '';
  const language = className.match(/(?:language-|lang-)([\w+-]+)/)?.[1] ?? 'text';
  const source = reactNodeText(children).replace(/\n$/, '');
  return <div className="message-code"><header><span>{language}</span><button type="button" onClick={() => navigator.clipboard?.writeText(source)}>Copy</button></header><pre>{children}</pre></div>;
}

export function reactNodeText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(reactNodeText).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) return reactNodeText(node.props.children);
  return '';
}
