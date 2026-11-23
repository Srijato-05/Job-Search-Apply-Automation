import { useEffect, useState } from 'react';
import { Download, Plus, Save, Trash2, Upload } from 'lucide-react';
import { api } from '../api/client';
import type { FactVaultData, QARuleItem } from '../api/types';

export function FactVaultPage() {
  const [vault, setVault] = useState<FactVaultData | null>(null);
  const [citiesInput, setCitiesInput] = useState('');
  const [blacklistInput, setBlacklistInput] = useState('');
  const [negKeywordsInput, setNegKeywordsInput] = useState('');
  const [qaRules, setQaRules] = useState<QARuleItem[]>([]);
  const [newQ, setNewQ] = useState('');
  const [newA, setNewA] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function loadAll() {
    try {
      const [v, rules] = await Promise.all([api.getVault(), api.listQaRules()]);
      setVault(v);
      setCitiesInput(v.preferred_cities_json.join(', '));
      setBlacklistInput(v.company_blacklist_json.join(', '));
      setNegKeywordsInput(v.negative_keywords_json.join(', '));
      setQaRules(rules);
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleSaveVault(e: React.FormEvent) {
    e.preventDefault();
    if (!vault) return;
    setErrorMsg(null);
    setStatusMsg(null);
    try {
      const payload: FactVaultData = {
        ...vault,
        preferred_cities_json: citiesInput.split(',').map((s) => s.trim()).filter(Boolean),
        company_blacklist_json: blacklistInput.split(',').map((s) => s.trim()).filter(Boolean),
        negative_keywords_json: negKeywordsInput.split(',').map((s) => s.trim()).filter(Boolean),
      };
      const updated = await api.updateVault(payload);
      setVault(updated);
      setStatusMsg('Fact Vault saved.');
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  }

  async function handleAddRule(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);
    try {
      await api.createQaRule({ question: newQ, verified_answer: newA });
      setNewQ('');
      setNewA('');
      setQaRules(await api.listQaRules());
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  }

  async function handleDeleteRule(id: number) {
    await api.deleteQaRule(id);
    setQaRules(await api.listQaRules());
  }

  async function handleExportZip() {
    try {
      const blob = await api.downloadBackupZip();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `jobautomation_backup_${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setStatusMsg('Backup ZIP downloaded.');
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  }

  async function handleRestoreZip(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setErrorMsg(null);
    try {
      const res = await api.restoreBackupZip(file);
      setStatusMsg(res.message);
      loadAll();
    } catch (err) {
      setErrorMsg((err as Error).message);
    }
  }

  if (!vault) {
    return <p className="text-sm text-slate-400">{errorMsg ?? 'Loading Fact Vault…'}</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">India Fact Vault & Backups</h1>
          <p className="text-sm text-slate-400">
            Single source of truth for LPA compensation, Notice/LWD, BGV facts, PII guardrails & ZIP backups
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportZip}
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700"
          >
            <Download className="h-4 w-4" /> Export ZIP Backup
          </button>
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800">
            <Upload className="h-4 w-4" /> Restore ZIP
            <input type="file" accept=".zip" onChange={handleRestoreZip} className="hidden" />
          </label>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-200">
          {statusMsg}
        </div>
      )}
      {errorMsg && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSaveVault} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Full Name</span>
            <input
              type="text"
              value={vault.full_name}
              onChange={(e) => setVault({ ...vault, full_name: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Email</span>
            <input
              type="email"
              value={vault.email}
              onChange={(e) => setVault({ ...vault, email: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Phone</span>
            <input
              type="text"
              value={vault.phone}
              onChange={(e) => setVault({ ...vault, phone: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Current CTC (LPA)</span>
            <input
              type="number"
              step="0.5"
              value={vault.current_ctc_lpa}
              onChange={(e) => setVault({ ...vault, current_ctc_lpa: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Expected CTC (LPA)</span>
            <input
              type="number"
              step="0.5"
              value={vault.expected_ctc_lpa}
              onChange={(e) => setVault({ ...vault, expected_ctc_lpa: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Notice Period (Days)</span>
            <input
              type="number"
              value={vault.notice_period_days}
              onChange={(e) => setVault({ ...vault, notice_period_days: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Total Experience (Years)</span>
            <input
              type="number"
              step="0.5"
              value={vault.total_exp_years}
              onChange={(e) => setVault({ ...vault, total_exp_years: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Current City</span>
            <input
              type="text"
              value={vault.current_city}
              onChange={(e) => setVault({ ...vault, current_city: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Max Apps / Company (30d)</span>
            <input
              type="number"
              value={vault.max_company_apps_30d}
              onChange={(e) => setVault({ ...vault, max_company_apps_30d: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Preferred Cities (comma-separated)</span>
            <input
              type="text"
              value={citiesInput}
              onChange={(e) => setCitiesInput(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Company Blacklist</span>
            <input
              type="text"
              value={blacklistInput}
              onChange={(e) => setBlacklistInput(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">Negative Title Keywords (Gate 1)</span>
            <input
              type="text"
              value={negKeywordsInput}
              onChange={(e) => setNegKeywordsInput(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
        </div>

        <button
          type="submit"
          className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
        >
          <Save className="h-4 w-4" /> Save Fact Vault
        </button>
      </form>

      {/* Learned Q&A Rules */}
      <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
        <h2 className="text-base font-semibold text-white">
          Learned Q&amp;A Rules (PII-Guarded: PAN / Aadhaar / DoB / Passport Blocked)
        </h2>
        <form onSubmit={handleAddRule} className="flex flex-wrap gap-2">
          <input
            type="text"
            required
            value={newQ}
            onChange={(e) => setNewQ(e.target.value)}
            placeholder="Normalized question (e.g. Are you comfortable with relocation?)"
            className="flex-1 min-w-[240px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
          />
          <input
            type="text"
            required
            value={newA}
            onChange={(e) => setNewA(e.target.value)}
            placeholder="Verified answer"
            className="w-60 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          >
            <Plus className="h-4 w-4" /> Add Rule
          </button>
        </form>

        <div className="divide-y divide-slate-800">
          {qaRules.map((rule) => (
            <div key={rule.id} className="flex items-center justify-between py-2.5 text-xs">
              <div>
                <div className="font-medium text-slate-200">{rule.normalized_question}</div>
                <div className="text-emerald-300">Answer: {rule.verified_answer}</div>
              </div>
              <button
                onClick={() => handleDeleteRule(rule.id)}
                className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-rose-400"
                aria-label={`Delete rule ${rule.id}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

