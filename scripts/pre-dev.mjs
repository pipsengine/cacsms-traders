/**
 * Free dev ports before starting API + Vite (avoids stale servers without MetaTrader5).
 */
import { execSync } from 'node:child_process';

const ports = [8000, 5173, 5174];

for (const port of ports) {
  try {
    if (process.platform === 'win32') {
      const pids = new Set();
      try {
        const ps = execSync(
          `powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`,
          { encoding: 'utf8' },
        );
        for (const pid of ps.split(/\r?\n/).map((s) => s.trim()).filter((s) => /^\d+$/.test(s))) {
          pids.add(pid);
        }
      } catch {
        /* fall back to netstat */
      }
      try {
        const out = execSync(`netstat -ano | findstr ":${port}" | findstr LISTENING`, { encoding: 'utf8' });
        for (const line of out.split(/\r?\n/)) {
          const pid = line.trim().split(/\s+/).pop();
          if (pid && /^\d+$/.test(pid)) pids.add(pid);
        }
      } catch {
        /* nothing listening */
      }
      for (const pid of pids) {
        try {
          execSync(`taskkill /F /PID ${pid}`, { stdio: 'ignore' });
          console.log(`[pre-dev] Stopped PID ${pid} on port ${port}`);
        } catch {
          try {
            execSync(
              `powershell -NoProfile -Command "Stop-Process -Id ${pid} -Force -ErrorAction Stop"`,
              { stdio: 'ignore' },
            );
            console.log(`[pre-dev] Stop-Process PID ${pid} on port ${port}`);
          } catch {
            /* already gone or protected */
          }
        }
      }
    } else {
      execSync(`npx --yes kill-port ${port}`, { stdio: 'inherit' });
    }
  } catch {
    /* nothing listening */
  }
}
