import React from 'react';

// Deliberately limited Markdown: source HTML, embeds and local-file links are text.
function Inline({ text }) {
  return String(text)
    .split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\s)]+\))/g)
    .map((token, index) => {
      if (token.startsWith('`') && token.endsWith('`'))
        return <code key={index}>{token.slice(1, -1)}</code>;
      if (token.startsWith('**') && token.endsWith('**'))
        return <strong key={index}>{token.slice(2, -2)}</strong>;
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        if (['TERMS.md', 'README.md'].includes(link[2]))
          return (
            <button
              key={index}
              type="button"
              className="dataset-about-link"
              data-document={link[2]}
            >
              {link[1]}
            </button>
          );
        if (/^https?:\/\//i.test(link[2]))
          return (
            <a key={index} href={link[2]} target="_blank" rel="noopener noreferrer">
              {link[1]}
            </a>
          );
        return link[1];
      }
      return token;
    });
}
export function DatasetDocument({ text }) {
  const lines = String(text).replace(/\r/g, '').split('\n'),
    output = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i],
      key = i;
    if (!line.trim()) continue;
    if (line.startsWith('```')) {
      const code = [];
      while (++i < lines.length && !lines[i].startsWith('```')) code.push(lines[i]);
      output.push(
        <pre key={key}>
          <code>{code.join('\n')}</code>
        </pre>,
      );
    } else if (/^#{1,6} /.test(line))
      output.push(
        <h3 key={key}>
          <Inline text={line.replace(/^#+ /, '')} />
        </h3>,
      );
    else if (/^\s*[-*] /.test(line)) {
      const items = [line];
      while (/^\s*[-*] /.test(lines[i + 1] || '')) items.push(lines[++i]);
      output.push(
        <ul key={key}>
          {items.map((item, index) => (
            <li key={index}>
              <Inline text={item.replace(/^\s*[-*] /, '')} />
            </li>
          ))}
        </ul>,
      );
    } else if (line.startsWith('|') && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      const cells = (value) =>
        value
          .trim()
          .replace(/^\||\|$/g, '')
          .split('|');
      const headers = cells(line),
        rows = [];
      i++;
      while ((lines[i + 1] || '').startsWith('|')) rows.push(cells(lines[++i]));
      output.push(
        <div key={key} className="dataset-about-table">
          <table>
            <thead>
              <tr>
                {headers.map((cell, index) => (
                  <th key={index}>
                    <Inline text={cell} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, j) => (
                    <td key={j}>
                      <Inline text={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else {
      const paragraph = [line];
      while (lines[i + 1]?.trim() && !/^(#|```|\||\s*[-*] )/.test(lines[i + 1]))
        paragraph.push(lines[++i]);
      output.push(
        <p key={key}>
          <Inline text={paragraph.join(' ')} />
        </p>,
      );
    }
  }
  return output;
}
