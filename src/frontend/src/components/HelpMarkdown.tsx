import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function HelpMarkdown({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mt-2 text-base font-semibold text-slate-100">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 text-sm font-semibold uppercase tracking-wide text-slate-300">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {children}
            </h3>
          ),
          a: ({ children, href }) => (
            <a className="text-bergt-green hover:underline" href={href}>
              {children}
            </a>
          ),
          ul: ({ children }) => <ul className="ml-4 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="ml-4 list-decimal space-y-1">{children}</ol>,
          code: ({ children }) => (
            <code className="rounded bg-slate-800 px-1 py-0.5 text-xs">{children}</code>
          ),
          table: ({ children }) => (
            <table className="my-2 w-full text-left text-xs">{children}</table>
          ),
          th: ({ children }) => <th className="border-b border-slate-700 py-1">{children}</th>,
          td: ({ children }) => <td className="border-b border-slate-800 py-1">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
