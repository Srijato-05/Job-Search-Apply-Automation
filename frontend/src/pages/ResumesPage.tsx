import { useEffect, useState } from 'react';
import { RefreshCw, Trash2, Upload } from 'lucide-react';
import { api } from '../api/client';
import type { ResumeDetail, ResumeSummary } from '../api/types';

export function ResumesPage() {
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [selectedDetail, setSelectedDetail] = useState<ResumeDetail | null>(null);
  const [trackName, setTrackName] = useState('');
  const [targetTitles, setTargetTitles] = useState('');
  const [searchLocations, setSearchLocations] = useState('Bengaluru, Hyderabad');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function loadResumes() {
    setResumes(await api.listResumes());
  }

  useEffect(() => {
    loadResumes();
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!pdfFile || !trackName.trim()) return;
    const fd = new FormData();
    fd.append('file', pdfFile);
    fd.append('track_name', trackName.trim());
    fd.append('target_titles', targetTitles);
    fd.append('search_locations', searchLocations);
    const created = await api.uploadResume(fd);
    setTrackName('');
    setTargetTitles('');
    setPdfFile(null);
    setMessage(`Uploaded "${created.track_name}" (${created.bullet_count} bullets embedded).`);
    loadResumes();
  }

  async function handleReparse(id: number) {
    const detail = await api.reparseResume(id);
    setSelectedDetail(detail);
    setMessage(`Reparsed "${detail.track_name}" (${detail.bullet_count} bullets).`);
    loadResumes();
  }

  async function handleDelete(id: number) {
    await api.deleteResume(id);
    if (selectedDetail?.id === id) setSelectedDetail(null);
    loadResumes();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Multi-Resume Tracks</h1>
        <p className="text-sm text-slate-400">
          Upload tailored PDF tracks; FastEmbed ONNX vectorizes every verbatim bullet locally for Option 3 matching
        </p>
      </div>

      {message && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-200">
          {message}
        </div>
      )}

      <form onSubmit={handleUpload} className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4 md:grid-cols-4">
        <input
          type="text"
          required
          value={trackName}
          onChange={(e) => setTrackName(e.target.value)}
          placeholder="Track Name (e.g. Backend Python)"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />
        <input
          type="text"
          value={targetTitles}
          onChange={(e) => setTargetTitles(e.target.value)}
          placeholder="Target Titles (comma-separated)"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />
        <input
          type="text"
          value={searchLocations}
          onChange={(e) => setSearchLocations(e.target.value)}
          placeholder="Target Cities"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />
        <div className="flex items-center gap-2">
          <input
            type="file"
            accept=".pdf"
            required
            onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
            className="w-full text-xs text-slate-300"
          />
          <button
            type="submit"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500"
          >
            <Upload className="h-3.5 w-3.5" /> Upload
          </button>
        </div>
      </form>

      <div className="grid gap-4 md:grid-cols-2">
        {resumes.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-2">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-semibold text-white">{r.track_name}</h3>
                <p className="text-xs text-slate-400">
                  {r.pdf_filename} • {r.bullet_count} embedded bullets
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => api.getResumeDetail(r.id).then(setSelectedDetail)}
                  className="rounded border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Bullets
                </button>
                <button
                  onClick={() => handleReparse(r.id)}
                  className="rounded border border-slate-700 p-1.5 text-slate-300 hover:bg-slate-800"
                  aria-label="Reparse resume"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleDelete(r.id)}
                  className="rounded border border-slate-700 p-1.5 text-rose-400 hover:bg-slate-800"
                  aria-label="Delete resume"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1">
              {r.track_skills_json.slice(0, 12).map((sk) => (
                <span key={sk} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-sky-300">
                  {sk}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {selectedDetail && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">
            Extracted Verbatim Bullets — {selectedDetail.track_name} ({selectedDetail.bullets.length})
          </h3>
          <ul className="space-y-2 text-xs text-slate-300">
            {selectedDetail.bullets.map((b) => (
              <li key={b.id} className="rounded border border-slate-800 bg-slate-950 p-2.5">
                <span className="mr-2 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                  {b.section_name}
                </span>
                {b.bullet_text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

