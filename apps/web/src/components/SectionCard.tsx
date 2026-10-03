import type { ReactNode } from 'react';
import { Card } from './Ui';

export function SectionCard({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Card className="section-card">
      <div className="section-card-head">
        <div>
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      <div className="section-card-body">{children}</div>
    </Card>
  );
}
