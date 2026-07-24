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
import type { DataTable, TabId } from './types';

const ACCENT = '#7c8cff';

export interface JumpTarget {
  table: DataTable;
  id: string;
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [jobActive, setJobActive] = useState(false);
  const [jumpTarget, setJumpTarget] = useState<JumpTarget | null>(null);
  const { data, refreshing, error, forceRefresh } = useDashboardData(jobActive);
  const report = data?.validationReport ?? null;

  const jumpToRow = (table: DataTable, id: string) => {
    setJumpTarget({ table, id });
    setActiveTab('data');
  };

  return (
    <div className="app-shell">
      <Header refreshing={refreshing} runId={report?.run_id} generatedAt={report?.generated_at} jobActive={jobActive} />
      <TabBar activeTab={activeTab} onChange={setActiveTab} />

      {error && activeTab !== 'pipeline' && (
        <div className="center-message live-empty">
          <strong>Waiting for the next live run.</strong>
          <p className="empty-state-detail">
            Open the <button type="button" className="link-btn" onClick={() => setActiveTab('pipeline')}>Pipeline</button>{' '}
            tab and run a job to populate the dashboard from the latest files in <code>public/data/</code>.
          </p>
        </div>
      )}

      <div style={{ display: activeTab === 'pipeline' ? 'block' : 'none' }}>
        <PipelineTab
          report={report}
          accent={ACCENT}
          onJobActiveChange={setJobActive}
          onJobComplete={forceRefresh}
        />
      </div>

      {activeTab !== 'pipeline' && !error && !data && (
        <div className="center-message live-empty">
          <strong>Fetching live pipeline output…</strong>
          <p className="empty-state-detail">The dashboard will show the newest generated bundle as soon as the API writes the live files.</p>
        </div>
      )}

      {data && (
        <>
          <div style={{ display: activeTab === 'overview' ? 'block' : 'none' }}>
            <OverviewTab
              report={data.validationReport}
              auditLogs={data.auditLogs}
              violations={data.violations}
              accent={ACCENT}
              jobActive={jobActive}
              onJump={jumpToRow}
            />
          </div>
          <div style={{ display: activeTab === 'validation' ? 'block' : 'none' }}>
            <ValidationTab report={data.validationReport} violations={data.violations} jobActive={jobActive} onJump={jumpToRow} />
          </div>
          <div style={{ display: activeTab === 'data' ? 'block' : 'none' }}>
            <DataTab
              auditLogs={data.auditLogs}
              violations={data.violations}
              qaPairs={data.qaPairs}
              jobActive={jobActive}
              jumpTarget={jumpTarget}
              onJumpConsumed={() => setJumpTarget(null)}
            />
          </div>
          <div style={{ display: activeTab === 'copilot' ? 'block' : 'none' }}>
            <CopilotTab violations={data.violations} auditLogs={data.auditLogs} jobActive={jobActive} onJump={jumpToRow} />
          </div>
          <div style={{ display: activeTab === 'proof' ? 'block' : 'none' }}>
            <ProofTab report={data.validationReport} accent={ACCENT} jobActive={jobActive} />
          </div>
        </>
      )}
    </div>
  );
}

export default App;
