import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const output = new URL('../static/js/react/', import.meta.url);
await mkdir(output, { recursive: true });
await build({
  absWorkingDir: fileURLToPath(new URL('.', import.meta.url)),
  entryPoints: ['src/patients.jsx'],
  outfile: fileURLToPath(new URL('patients.js', output)),
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2020',
  jsx: 'automatic',
  minify: true,
  define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'linked',
});
const licences = await Promise.all(['react', 'react-dom', 'scheduler'].map(async name =>
  `${name}\n${await readFile(new URL(`node_modules/${name}/LICENSE`, import.meta.url), 'utf8')}`));
await writeFile(new URL('LICENSES.txt', output), licences.join('\n\n'));
