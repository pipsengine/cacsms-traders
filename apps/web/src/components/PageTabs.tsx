import React from 'react';

export function PageTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="page-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          type="button"
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className={active === t.id ? 'page-tab active' : 'page-tab'}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ active, id, children }: { active: string; id: string; children: React.ReactNode }) {
  if (active !== id) return null;
  return <div className="tab-panel">{children}</div>;
}
