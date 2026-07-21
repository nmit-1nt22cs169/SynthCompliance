import { useEffect, useRef, useState } from 'react';
import { loadDashboardData } from '../lib/dataLoader';
import type { DashboardData } from '../types';

const REFRESH_INTERVAL_MS = 9000;
const REFRESHING_INDICATOR_MS = 1200;

interface DashboardDataState {
  data: DashboardData | null;
  refreshing: boolean;
  error: string | null;
}

export function useDashboardData(): DashboardDataState {
  const [data, setData] = useState<DashboardData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;

    const load = async (isRefresh: boolean) => {
      if (isRefresh) setRefreshing(true);
      try {
        const fresh = await loadDashboardData();
        if (mounted.current) {
          setData(fresh);
          setError(null);
        }
      } catch (err) {
        if (mounted.current) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (isRefresh) {
          setTimeout(() => {
            if (mounted.current) setRefreshing(false);
          }, REFRESHING_INDICATOR_MS);
        }
      }
    };

    load(false);
    const interval = setInterval(() => load(true), REFRESH_INTERVAL_MS);

    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
  }, []);

  return { data, refreshing, error };
}
