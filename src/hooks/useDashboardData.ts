import { useCallback, useEffect, useRef, useState } from 'react';
import { loadDashboardData } from '../lib/dataLoader';
import type { DashboardData } from '../types';

const REFRESH_INTERVAL_MS = 9000;
const FAST_POLL_MS = 2000;
const REFRESHING_INDICATOR_MS = 1200;

interface DashboardDataState {
  data: DashboardData | null;
  refreshing: boolean;
  error: string | null;
  forceRefresh: () => void;
}

export function useDashboardData(jobActive = false): DashboardDataState {
  const [data, setData] = useState<DashboardData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const load = useCallback(async (isRefresh: boolean) => {
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
  }, []);

  const forceRefresh = useCallback(() => {
    load(true);
  }, [load]);

  useEffect(() => {
    mounted.current = true;
    load(false);
    const intervalMs = jobActive ? FAST_POLL_MS : REFRESH_INTERVAL_MS;
    const interval = setInterval(() => load(true), intervalMs);
    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
  }, [load, jobActive]);

  return { data, refreshing, error, forceRefresh };
}
