export function SubTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="sub-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          type="button"
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className={active === t.id ? 'sub-tab active' : 'sub-tab'}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
