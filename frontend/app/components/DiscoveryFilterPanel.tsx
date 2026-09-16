"use client";

import React from "react";
import { Filter, RotateCcw, AlertTriangle, Users, Calendar, Clock, Check } from "lucide-react";

export interface FilterOptions {
  available: boolean;
  resources: string[];
  date_range: {
    min: string | null;
    max: string | null;
    min_date: string | null;
    max_date: string | null;
  };
  duration_hours: {
    min: number;
    max: number;
  };
  total_cases: number;
}

export interface ActiveFilters {
  startDate: string;
  endDate: string;
  selectedResources: string[];
  minDuration: string;
  maxDuration: string;
}

interface DiscoveryFilterPanelProps {
  options: FilterOptions | null;
  filters: ActiveFilters;
  onFilterChange: (filters: ActiveFilters) => void;
  onClearFilters: () => void;
  matchedCases?: number | null;
  totalCases?: number | null;
  isFiltered: boolean;
  isLoading?: boolean;
}

export const DiscoveryFilterPanel: React.FC<DiscoveryFilterPanelProps> = ({
  options,
  filters,
  onFilterChange,
  onClearFilters,
  matchedCases,
  totalCases,
  isFiltered,
  isLoading = false,
}) => {
  if (!options || !options.available) {
    return null;
  }

  const allResources = options.resources || [];
  const minBoundDate = options.date_range?.min_date || "";
  const maxBoundDate = options.date_range?.max_date || "";
  const minBoundDur = options.duration_hours?.min ?? 0;
  const maxBoundDur = options.duration_hours?.max ?? 100;
  const displayTotal = totalCases ?? options.total_cases ?? 0;
  const displayMatched = matchedCases ?? displayTotal;

  const handleStartDateChange = (val: string) => {
    onFilterChange({ ...filters, startDate: val });
  };

  const handleEndDateChange = (val: string) => {
    onFilterChange({ ...filters, endDate: val });
  };

  const handleToggleResource = (resName: string) => {
    const current = new Set(filters.selectedResources);
    if (current.has(resName)) {
      current.delete(resName);
    } else {
      current.add(resName);
    }
    onFilterChange({ ...filters, selectedResources: Array.from(current) });
  };

  const handleSelectAllResources = () => {
    onFilterChange({ ...filters, selectedResources: [...allResources] });
  };

  const handleDeselectAllResources = () => {
    onFilterChange({ ...filters, selectedResources: [] });
  };

  const handleMinDurationChange = (val: string) => {
    onFilterChange({ ...filters, minDuration: val });
  };

  const handleMaxDurationChange = (val: string) => {
    onFilterChange({ ...filters, maxDuration: val });
  };

  const notEnoughCases = displayMatched < 2;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl backdrop-blur-md mb-6 transition-all">
      {/* Top Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Filter className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
              Discovery Event Log Filtering
              {isLoading && (
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              )}
            </h3>
            <p className="text-[11px] text-slate-400">
              Narrow process graph and bottlenecks by timeframe, resource, or case duration in-memory
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Live Count Badge */}
          <div
            className={`px-3 py-1 rounded-full text-xs font-mono font-semibold flex items-center gap-1.5 transition-colors ${
              notEnoughCases
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                : isFiltered
                ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40"
                : "bg-slate-800/80 text-slate-300 border border-slate-700/60"
            }`}
          >
            <span>
              Showing <strong className="text-white">{displayMatched}</strong> of {displayTotal} cases
            </span>
            {isFiltered && !notEnoughCases && (
              <span className="px-1.5 py-0.2 rounded text-[9px] font-sans font-bold bg-indigo-500/30 uppercase tracking-wider">
                Filtered
              </span>
            )}
          </div>

          {/* Reset / Clear Button */}
          {isFiltered && (
            <button
              type="button"
              onClick={onClearFilters}
              className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 flex items-center gap-1.5 transition-colors"
              title="Reset all filters to default"
            >
              <RotateCcw className="w-3 h-3 text-slate-400" />
              <span>Clear filters</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Controls Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 text-xs">
        {/* 1. Date Range Picker */}
        <div className="space-y-2 bg-slate-950/40 p-3 rounded-xl border border-slate-800/60">
          <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-indigo-400" />
            <span>Timeframe (Case Start Date)</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-[10px] text-slate-500 block mb-1">From:</span>
              <input
                type="date"
                min={minBoundDate}
                max={filters.endDate || maxBoundDate}
                value={filters.startDate}
                onChange={(e) => handleStartDateChange(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block mb-1">To:</span>
              <input
                type="date"
                min={filters.startDate || minBoundDate}
                max={maxBoundDate}
                value={filters.endDate}
                onChange={(e) => handleEndDateChange(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* 2. Duration Bounds */}
        <div className="space-y-2 bg-slate-950/40 p-3 rounded-xl border border-slate-800/60">
          <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            <span>Case Duration (Hours)</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-[10px] text-slate-500 block mb-1">Min (≥ {minBoundDur}h):</span>
              <input
                type="number"
                step="0.5"
                min={minBoundDur}
                max={maxBoundDur}
                placeholder={minBoundDur.toString()}
                value={filters.minDuration}
                onChange={(e) => handleMinDurationChange(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:border-indigo-500 focus:outline-none font-mono"
              />
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block mb-1">Max (≤ {maxBoundDur}h):</span>
              <input
                type="number"
                step="0.5"
                min={minBoundDur}
                max={maxBoundDur}
                placeholder={maxBoundDur.toString()}
                value={filters.maxDuration}
                onChange={(e) => handleMaxDurationChange(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:border-indigo-500 focus:outline-none font-mono"
              />
            </div>
          </div>
        </div>

        {/* 3. Resource Multi-Select */}
        <div className="space-y-2 bg-slate-950/40 p-3 rounded-xl border border-slate-800/60">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-indigo-400" />
              <span>Resources ({filters.selectedResources.length}/{allResources.length})</span>
            </label>
            <div className="flex items-center gap-1 text-[10px]">
              <button
                type="button"
                onClick={handleSelectAllResources}
                className="text-indigo-400 hover:text-indigo-300 font-medium px-1"
              >
                All
              </button>
              <span className="text-slate-600">|</span>
              <button
                type="button"
                onClick={handleDeselectAllResources}
                className="text-slate-400 hover:text-slate-300 font-medium px-1"
              >
                None
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5 max-h-[70px] overflow-y-auto pr-1">
            {allResources.map((resName) => {
              const isSelected = filters.selectedResources.includes(resName);
              return (
                <button
                  key={resName}
                  type="button"
                  onClick={() => handleToggleResource(resName)}
                  className={`px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors border flex items-center gap-1 ${
                    isSelected
                      ? "bg-indigo-600/30 border-indigo-500/60 text-indigo-200"
                      : "bg-slate-900/60 border-slate-800 text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {isSelected && <Check className="w-2.5 h-2.5 text-indigo-400" />}
                  <span>{resName}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Graceful < 2 cases warning notice */}
      {notEnoughCases && (
        <div className="mt-3.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center justify-between text-xs animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Not enough cases match these filters to discover a process</strong> (found {displayMatched} cases; minimum 2 required). Showing empty graph and bottleneck tables.
            </span>
          </div>
          <button
            type="button"
            onClick={onClearFilters}
            className="px-2.5 py-1 rounded-md bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 font-semibold text-[11px] transition-colors shrink-0"
          >
            Reset Filters
          </button>
        </div>
      )}
    </div>
  );
};
