/**
 * Sanitized Markdown renderer shared by issue threads and knowledge pages.
 *
 * Text written by people or the agent is untrusted: raw HTML is dropped and
 * rehype-sanitize strips anything outside GitHub's allow-list (scripts, event
 * handlers, javascript: links). GitHub-flavoured Markdown adds tables, task
 * lists, strikethrough and autolinks.
 */

import type { ComponentProps } from "react";
import ReactMarkdown, {
  type Components,
  type ExtraProps,
} from "react-markdown";
import { Link, useInRouterContext } from "react-router-dom";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

import { cn } from "@/lib/utils";

const LINK_CLASS = "text-primary underline underline-offset-2";

/**
 * A link to a page of the app, like the credentials page the agent points to,
 * opens in place. Anything else opens in a new tab.
 */
function MarkdownLink({
  node: _node,
  href,
  ...props
}: ComponentProps<"a"> & ExtraProps) {
  const inRouter = useInRouterContext();
  if (inRouter && href?.startsWith("/") && !href.startsWith("//")) {
    return <Link to={href} className={LINK_CLASS} {...props} />;
  }
  return (
    <a
      href={href}
      className={LINK_CLASS}
      target="_blank"
      rel="noopener noreferrer nofollow"
      {...props}
    />
  );
}

const components: Components = {
  p: ({ node: _node, ...props }) => (
    <p className="my-1.5 first:mt-0 last:mb-0" {...props} />
  ),
  a: MarkdownLink,
  ul: ({ node: _node, ...props }) => (
    <ul className="my-1.5 list-disc pl-5" {...props} />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol className="my-1.5 list-decimal pl-5" {...props} />
  ),
  li: ({ node: _node, ...props }) => <li className="my-0.5" {...props} />,
  h1: ({ node: _node, ...props }) => (
    <h1 className="mb-1.5 mt-3 text-base font-semibold first:mt-0" {...props} />
  ),
  h2: ({ node: _node, ...props }) => (
    <h2 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0" {...props} />
  ),
  h3: ({ node: _node, ...props }) => (
    <h3 className="mb-1 mt-2 text-sm font-semibold first:mt-0" {...props} />
  ),
  blockquote: ({ node: _node, ...props }) => (
    <blockquote
      className="my-1.5 border-l-2 border-border pl-3 text-muted-foreground"
      {...props}
    />
  ),
  pre: ({ node: _node, ...props }) => (
    <pre
      className="my-1.5 overflow-x-auto rounded-md bg-muted p-2 font-mono text-xs [&>code]:bg-transparent [&>code]:p-0"
      {...props}
    />
  ),
  code: ({ node: _node, className, ...props }) => (
    <code
      className={cn(
        "rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]",
        className,
      )}
      {...props}
    />
  ),
  table: ({ node: _node, ...props }) => (
    <div className="my-1.5 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  th: ({ node: _node, ...props }) => (
    <th
      className="border-b border-border px-2 py-1 text-left font-semibold text-muted-foreground"
      {...props}
    />
  ),
  td: ({ node: _node, ...props }) => (
    <td className="border-b border-border px-2 py-1" {...props} />
  ),
  hr: ({ node: _node, ...props }) => (
    <hr className="my-2 border-border" {...props} />
  ),
};

interface MarkdownProps {
  children: string;
  className?: string;
}

export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div className={cn("break-words text-sm leading-relaxed", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
