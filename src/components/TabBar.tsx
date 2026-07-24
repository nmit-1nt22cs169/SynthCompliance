import type { TabId } from '../types';

const TAB_DEFS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'validation', label: 'Validation' },
  { id: 'data', label: 'Data' },
  { id: 'copilot', label: 'Copilot' },
  { id: 'proof', label: 'Proof' }
];

interface TabBarProps {
  activeTab: TabId;
  onChange: (id: TabId) => void;
}

export function TabBar({ activeTab, onChange }: TabBarProps) {
  return (
    <div className="tab-bar">
      {TAB_DEFS.map((t) => (
        <div
          key={t.id}
          role="tab"
          aria-selected={activeTab === t.id}
          tabIndex={0}
          className={`tab-item${activeTab === t.id ? ' active' : ''}`}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onChange(t.id);
          }}
        >
          {t.label}
        </div>
      ))}
    </div>
  );
}
