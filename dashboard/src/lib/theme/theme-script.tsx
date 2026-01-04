export function ThemeScript() {
  const script = `
    (function() {
      const stored = localStorage.getItem('datadr-theme');
      const theme = stored || 'system';
      const resolved = theme === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : theme;
      document.documentElement.setAttribute('data-theme', resolved);
    })();
  `;

  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
