import { useState } from 'react';
import { Header } from './components/Header';
import { TabBar } from './components/TabBar';
import { OverviewTab } from './components/tabs/OverviewTab';
import { PipelineTab } from './components/tabs/PipelineTab';
import { ValidationTab } from './components/tabs/ValidationTab';
import { DataTab } from './components/tabs/DataTab';
import { CopilotTab } from './components/tabs/CopilotTab';
import { ProofTab } from './components/tabs/ProofTab';
import { useDashboardData } from './hooks/useDashboardData';
import type { TabId } from './types';

const ACCENT = '#7c8cff';

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [jobActive, setJobActive] = useState(false);
  const { data, refreshing, error, forceRefresh } = useDashboardData(jobActive);
  const report = data?.validationReport ?? null;

  return (
    <div className="app-shell">
      <Header refreshing={refreshing} runId={report?.run_id} jobActive={jobActive} />
      <TabBar activeTab={activeTab} onChange={setActiveTab} />

      {error && activeTab !== 'pipeline' && (
        <div className="center-message live-empty">
          <strong>Waiting for the next live run.</strong>
          <p style={{ margin: '8px 0 0', fontSize: 13 }}>
            Open the <button type="button" className="link-btn" onClick={() => setActiveTab('pipeline')}>Pipeline</button>{' '}
            tab and run a job to populate the dashboard from the latest files in <code>public/data/</code>.
          </p>
        </div>
      )}

      {activeTab === 'pipeline' && (
        <PipelineTab
          report={report}
          accent={ACCENT}
          onJobActiveChange={setJobActive}
          onJobComplete={forceRefresh}
        />
      )}

      {activeTab !== 'pipeline' && !error && !data && (
        <div className="center-message live-empty">
          <strong>Fetching live pipeline output…</strong>
          <p style={{ margin: '8px 0 0', fontSize: 13 }}>The dashboard will show the newest generated bundle as soon as the API writes the live files.</p>
        </div>
      )}

      {data && activeTab !== 'pipeline' && (
        <>
          {activeTab === 'overview' && <OverviewTab report={data.validationReport} accent={ACCENT} />}
          {activeTab === 'validation' && <ValidationTab report={data.validationReport} />}
          {activeTab === 'data' && (
            <DataTab auditLogs={data.auditLogs} violations={data.violations} qaPairs={data.qaPairs} />
          )}
          {activeTab === 'copilot' && (
            <CopilotTab violations={data.violations} auditLogs={data.auditLogs} />
          )}
          {activeTab === 'proof' && <ProofTab report={data.validationReport} accent={ACCENT} />}
        </>
      )}
    </div>
  );
}

export default App;
