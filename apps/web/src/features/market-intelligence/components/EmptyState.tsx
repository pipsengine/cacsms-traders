import type { ReactNode } from 'react';

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="mi-empty">
      <div>◇</div>
      <h3>{title}</h3>
      <p>{body}</p>
      {action ? <div className="mi-empty-action">{action}</div> : null}
    </div>
  );
}
