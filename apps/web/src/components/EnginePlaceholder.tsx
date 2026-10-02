import { Layers } from 'lucide-react';
import { Card } from './Ui';

export function EnginePlaceholder({
  title,
  body,
  engine,
}: {
  title: string;
  body: string;
  engine?: string;
}) {
  return (
    <Card className="engine-placeholder">
      <div className="engine-placeholder-inner">
        <div className="engine-placeholder-icon">
          <Layers />
        </div>
        <div>
          <span className="engine-placeholder-kicker">Awaiting engine integration</span>
          <h2>{title}</h2>
          <p>{body}</p>
          {engine && (
            <p className="muted">
              Backend module: <code>{engine}</code>
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
