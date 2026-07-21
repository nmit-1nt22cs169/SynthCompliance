import { useState } from 'react';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { OverviewTab } from './components/tabs/OverviewTab';
import { PipelineTab } from './components/tabs/PipelineTab';
import { ValidationTab } from './components/tabs/ValidationTab';
import { DataTab } from './components/tabs/DataTab';
import { CopilotTab } from './components/tabs/CopilotTab';
import { useDashboardData } from './hooks/useDashboardData';
import type { TabId } from './types';

const ACCENT = '#7c8cff';

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const { data, refreshing, error } = useDashboardData();

  return (
    <div className="app-shell">
      <Header refreshing={refreshing} />
      <TabBar activeTab={activeTab} onChange={setActiveTab} />

      {error && <div className="center-message">Failed to load dashboard data: {error}</div>}

      {!error && !data && <div className="center-message">Loading…</div>}

      {data && (
        <>
          {activeTab === 'overview' && <OverviewTab report={data.validationReport} accent={ACCENT} />}
          {activeTab === 'pipeline' && <PipelineTab report={data.validationReport} accent={ACCENT} />}
          {activeTab === 'validation' && <ValidationTab report={data.validationReport} />}
          {activeTab === 'data' && (
            <DataTab auditLogs={data.auditLogs} violations={data.violations} qaPairs={data.qaPairs} />
          )}
          {activeTab === 'copilot' && <CopilotTab violations={data.violations} />}
        </>
      )}
    </div>
  );
}

export default App;
