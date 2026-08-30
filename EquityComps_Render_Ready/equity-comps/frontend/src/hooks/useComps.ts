import { useState, useEffect, useCallback, useRef } from 'react';
import { CompsResponse, FilterOptions, Filters, DataTimestamps } from '../types';
import { fetchComps, fetchFilterOptions } from '../services/api';

const DEFAULT_FILTERS: Filters = {
  universe: 'ALL',
  sector: '',
  industry: '',
  search: '',
  benchmarkMetric: 'ev_ebitda',
};

export function useComps() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [data, setData] = useState<CompsResponse | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    sectors: [], industries: [], universes: ['ALL', 'SP500', 'NASDAQ100'],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFetchKey = useRef<string>('');

  const loadFilterOptions = useCallback(async (sector?: string) => {
    try {
      setFilterOptions(await fetchFilterOptions(sector));
    } catch (e) {
      console.error('Filter options failed', e);
    }
  }, []);

  const loadData = useCallback(async (f: Filters) => {
    const key = JSON.stringify({
      universe: f.universe, sector: f.sector,
      industry: f.industry, search: f.search,
    });
    if (key === lastFetchKey.current) return;
    lastFetchKey.current = key;

    setLoading(true);
    setError(null);
    try {
      const result = await fetchComps({
        universe: f.universe,
        sector:   f.sector   || undefined,
        industry: f.industry || undefined,
        search:   f.search   || undefined,
      });
      setData(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial filter options load
  useEffect(() => { loadFilterOptions(); }, [loadFilterOptions]);

  // Re-fetch whenever non-benchmark filters change (benchmark is client-side only)
  useEffect(() => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    const delay = filters.search ? 400 : 0;
    searchTimeout.current = setTimeout(() => loadData(filters), delay);
    return () => { if (searchTimeout.current) clearTimeout(searchTimeout.current); };
  }, [filters.universe, filters.sector, filters.industry, filters.search, loadData]);

  const updateFilters = useCallback((updates: Partial<Filters>) => {
    setFilters(prev => {
      const next = { ...prev, ...updates };
      if (updates.sector !== undefined && updates.sector !== prev.sector) {
        next.industry = '';
        loadFilterOptions(updates.sector || undefined);
      }
      return next;
    });
    // Only force server refetch for non-benchmark changes
    if (!('benchmarkMetric' in updates)) {
      lastFetchKey.current = '';
    }
  }, [loadFilterOptions]);

  const refresh = useCallback(() => {
    lastFetchKey.current = '';
    loadData(filters);
  }, [filters, loadData]);

  // Expose timestamps from latest response
  const timestamps = data?.timestamps ?? null;

  return {
    filters, data, filterOptions,
    loading, error, timestamps,
    updateFilters, refresh,
  };
}
