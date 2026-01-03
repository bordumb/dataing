import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface SqlExplainerProps {
  sql: string
}

export function SqlExplainer({ sql }: SqlExplainerProps) {
  return (
    <div className="rounded-md overflow-hidden text-sm">
      <SyntaxHighlighter
        language="sql"
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: '1rem',
          fontSize: '0.75rem',
        }}
        wrapLines
        wrapLongLines
      >
        {sql}
      </SyntaxHighlighter>
    </div>
  )
}
