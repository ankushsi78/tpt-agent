import React, { useState, useEffect, useMemo } from 'react';
import { base44 } from '@/api/base44Client';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BarChart3, Users, Eye, RefreshCw } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// VisitStats — first-party traffic dashboard for the public Trader Stage Finder.
// Reads the PageVisit entity and reports Unique Daily Visitors (distinct
// visitor_id per visit_date) as a backup/cross-check to Google Analytics.
//
// KEEP THIS PAGE PRIVATE: in base44, set its access to admin/owner only — it is
// NOT meant to be public like the TraderStages page.
// ─────────────────────────────────────────────────────────────────────────────

const PAGE = 'TraderStages';

export default function VisitStats() {
  const [rows, setRows] = useState(null);   // null = loading
  const [error, setError] = useState(null);

  const load = async () => {
    setRows(null);
    setError(null);
    try {
      // Pull this page's visits, newest first. base44 .filter(query, sort, limit).
      const data = await base44.entities.PageVisit.filter({ page: PAGE }, '-visit_date', 10000);
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setError((e && e.message) || 'Failed to load visit data.');
      setRows([]);
    }
  };

  useEffect(() => { load(); }, []);

  // Aggregate: distinct visitor_id per date = unique daily visitors; row count = total views.
  const { daily, totalUnique, totalViews, last7Unique } = useMemo(() => {
    if (!rows) return { daily: [], totalUnique: 0, totalViews: 0, last7Unique: 0 };
    const byDate = new Map();          // date -> Set(visitor_id)
    const allVisitors = new Set();
    rows.forEach(r => {
      const d = r.visit_date || (r.created_date ? String(r.created_date).slice(0, 10) : 'unknown');
      if (!byDate.has(d)) byDate.set(d, new Set());
      byDate.get(d).add(r.visitor_id || r.id);
      allVisitors.add(r.visitor_id || r.id);
    });
    const daily = [...byDate.entries()]
      .map(([date, set]) => ({
        date,
        unique: set.size,
        views: rows.filter(r => (r.visit_date || '') === date).length,
      }))
      .sort((a, b) => (a.date < b.date ? 1 : -1)); // newest first

    const cutoff = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    const last7 = new Set();
    rows.forEach(r => { if ((r.visit_date || '') >= cutoff) last7.add(r.visitor_id || r.id); });

    return {
      daily,
      totalUnique: allVisitors.size,
      totalViews: rows.length,
      last7Unique: last7.size,
    };
  }, [rows]);

  const maxUnique = Math.max(1, ...daily.map(d => d.unique));

  const Stat = ({ icon: Icon, label, value, accent }) => (
    <Card className="border-slate-200 dark:border-slate-700 shadow-sm">
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <Icon className={`w-4 h-4 ${accent}`} /> {label}
        </div>
        <div className="mt-1 text-3xl font-bold text-slate-900 dark:text-slate-50">{value}</div>
      </CardContent>
    </Card>
  );

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 bg-indigo-500 rounded-xl flex items-center justify-center shadow">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">Trader Stage Finder — Traffic</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">First-party visit log (cross-check to Google Analytics)</p>
            </div>
          </div>
          <Button variant="outline" onClick={load} disabled={rows === null}>
            <RefreshCw className={`w-4 h-4 mr-2 ${rows === null ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>

        {error && (
          <div className="mt-6 rounded-lg border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/40 p-4 text-sm text-red-700 dark:text-red-300">
            {error} — confirm the <code>PageVisit</code> entity exists and you have read access.
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat icon={Users} label="Unique visitors (7 days)" value={rows === null ? '…' : last7Unique} accent="text-emerald-500" />
          <Stat icon={Users} label="Unique visitors (all time)" value={rows === null ? '…' : totalUnique} accent="text-indigo-500" />
          <Stat icon={Eye} label="Total page views" value={rows === null ? '…' : totalViews} accent="text-amber-500" />
        </div>

        <Card className="mt-8 border-slate-200 dark:border-slate-700 shadow-lg">
          <CardHeader className="border-b border-slate-100 dark:border-slate-700">
            <CardTitle className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              Unique Daily Visitors
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {rows === null ? (
              <p className="text-slate-500 dark:text-slate-400 py-6 text-center">Loading…</p>
            ) : daily.length === 0 ? (
              <p className="text-slate-500 dark:text-slate-400 py-6 text-center">
                No visits recorded yet. Once the public page gets traffic, daily numbers appear here.
              </p>
            ) : (
              <div className="space-y-2">
                {daily.map(d => (
                  <div key={d.date} className="flex items-center gap-3">
                    <div className="w-24 flex-none text-sm text-slate-500 dark:text-slate-400 tabular-nums">{d.date}</div>
                    <div className="flex-1 bg-slate-100 dark:bg-slate-800 rounded-full h-6 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full flex items-center justify-end px-2"
                        style={{ width: `${Math.max(6, (d.unique / maxUnique) * 100)}%` }}
                      >
                        <span className="text-xs font-semibold text-white tabular-nums">{d.unique}</span>
                      </div>
                    </div>
                    <div className="w-20 flex-none text-right text-xs text-slate-400 tabular-nums">{d.views} views</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          “Unique” = distinct anonymous visitor IDs (one per browser) seen on each date. Numbers may differ
          slightly from Google Analytics due to ad-blockers, cookie clearing, and bot filtering.
        </p>
      </div>
    </div>
  );
}
