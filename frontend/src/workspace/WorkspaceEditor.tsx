import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/basic-languages/css/css.contribution';
import 'monaco-editor/esm/vs/basic-languages/html/html.contribution';
import 'monaco-editor/esm/vs/basic-languages/ini/ini.contribution';
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution';
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution';
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution';
import 'monaco-editor/esm/vs/basic-languages/shell/shell.contribution';
import 'monaco-editor/esm/vs/basic-languages/sql/sql.contribution';
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution';
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution';

// Use the installed Monaco build instead of the loader's public CDN default. This keeps
// local and remote Gateway sessions deterministic and allows offline file inspection.
loader.config({ monaco });

export default function WorkspaceEditor({ filePath, language, content, theme }: {
  filePath: string;
  language: string;
  content: string;
  theme: 'dark' | 'light';
}) {
  return <Editor
    height="100%"
    path={filePath}
    language={language}
    value={content}
    theme={theme === 'dark' ? 'vs-dark' : 'light'}
    options={{
      readOnly: true,
      domReadOnly: true,
      minimap: { enabled: false },
      fontSize: 12,
      lineHeight: 19,
      folding: true,
      wordWrap: 'off',
      scrollBeyondLastLine: false,
      automaticLayout: true,
      renderValidationDecorations: 'off',
    }}
  />;
}
