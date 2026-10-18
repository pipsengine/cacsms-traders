/**
 * Start the API with a Python that can import stdlib (encodings).
 * Prefers .venv, then Windows py launcher tags, then python on PATH.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const runApi = join(root, 'scripts', 'run_api.py');
const venvPy =
  process.platform === 'win32'
    ? join(root, '.venv', 'Scripts', 'python.exe')
    : join(root, '.venv', 'bin', 'python');

/** @type {{ cmd: string; prefix: string[] }[]} */
const candidates = [];
if (existsSync(venvPy)) {
  candidates.push({ cmd: venvPy, prefix: [] });
}
if (process.platform === 'win32') {
  candidates.push({ cmd: 'py', prefix: ['-V:Astral/CPython3.14.4'] });
  candidates.push({ cmd: 'py', prefix: ['-3.14'] });
  candidates.push({ cmd: 'py', prefix: ['-3.12'] });
}
candidates.push({ cmd: 'python3', prefix: [] });
candidates.push({ cmd: 'python', prefix: [] });

function pythonWorks(cmd, prefix) {
  const r = spawnSync(cmd, [...prefix, '-c', 'import encodings'], {
    encoding: 'utf8',
    stdio: 'ignore',
  });
  return r.status === 0;
}

const chosen = candidates.find(({ cmd, prefix }) => pythonWorks(cmd, prefix));
if (!chosen) {
  console.error(
    '[run-api-dev] No working Python found. Create a venv:\n' +
      '  py -V:Astral/CPython3.14.4 -m venv .venv\n' +
      '  .venv\\Scripts\\pip install -r apps/api/requirements.txt',
  );
  process.exit(1);
}

const child = spawn(chosen.cmd, [...chosen.prefix, runApi], {
  cwd: root,
  stdio: 'inherit',
  env: process.env,
});
child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 1);
  }
});
