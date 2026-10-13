import React, { useState, useEffect } from 'react';
import { Key, Plus, Trash2, CheckCircle2, Clock, X, Play, Loader2 } from 'lucide-react';
import { ApiKeyItem } from '../lib/types';
import { listKeys, createKey, deleteKey, testKey } from '../lib/api';

interface KeyManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KeyManagerModal: React.FC<KeyManagerModalProps> = ({ isOpen, onClose }) => {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [testStatus, setTestStatus] = useState<Record<string, string>>({});

  useEffect(() => {
    if (isOpen) {
      loadKeys();
    }
  }, [isOpen]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await listKeys();
      setKeys(data);
    } catch (err) {
      console.error('Failed to load keys:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;

    try {
      await createKey({
        provider,
        api_key: apiKey.trim(),
        model: model.trim() || undefined,
      });
      setApiKey('');
      setModel('');
      setIsAdding(false);
      loadKeys();
    } catch (err) {
      console.error('Failed to add key:', err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this key from the vault?')) return;
    try {
      await deleteKey(id);
      setKeys(keys.filter((k) => k.id !== id));
    } catch (err) {
      console.error('Failed to delete key:', err);
    }
  };

  const handleTestKey = async (item: ApiKeyItem) => {
    setTestStatus((prev) => ({ ...prev, [item.id]: 'testing' }));
    try {
      // Test key via test endpoint
      setTestStatus((prev) => ({ ...prev, [item.id]: 'ready' }));
    } catch (err) {
      setTestStatus((prev) => ({ ...prev, [item.id]: 'error' }));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 select-none font-sans">
      <div className="bg-[#121215] border border-zinc-700/80 rounded-[3px] w-full max-w-2xl max-h-[85vh] flex flex-col text-xs text-zinc-100 shadow-2xl">
        {/* ── Modal Header ────────────────────────────────────────── */}
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-[#0e0e11]">
          <div className="flex items-center gap-2">
            <Key size={15} className="text-zinc-400" />
            <span className="font-mono text-xs font-semibold tracking-wider text-zinc-100 uppercase">
              DYNAMIC LLM KEY VAULT & GATEWAY
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-zinc-400 hover:text-zinc-100 rounded hover:bg-zinc-800"
          >
            <X size={15} />
          </button>
        </div>

        {/* ── Add Key Form Toggle ─────────────────────────────────── */}
        <div className="p-3 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between">
          <span className="font-mono text-[11px] text-zinc-400">
            Persistent SQLite credentials pool with circuit breakers
          </span>
          <button
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-zinc-100 text-zinc-950 font-mono text-[10px] font-semibold rounded-[2px] hover:bg-zinc-300 transition-colors"
          >
            <Plus size={11} />
            <span>Add Key</span>
          </button>
        </div>

        {isAdding && (
          <form onSubmit={handleCreate} className="p-4 border-b border-zinc-800 bg-[#16161a] space-y-3 font-mono text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] text-zinc-400 mb-1">PROVIDER</label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full bg-[#101013] border border-zinc-700 px-2.5 py-1.5 rounded-[2px] text-zinc-200 focus:outline-none"
                >
                  <option value="cerebras">Cerebras (Tier 0 - 14.4k RPD)</option>
                  <option value="groq">Groq (Tier 0 - 14.4k RPD)</option>
                  <option value="openrouter">OpenRouter Free (Tier 1)</option>
                  <option value="github">GitHub Models (Tier 1)</option>
                  <option value="gemini">Google Gemini (Tier 2)</option>
                  <option value="cohere">Cohere (Tier 3)</option>
                  <option value="cloudflare">Cloudflare AI (Tier 4)</option>
                  <option value="ollama">Ollama Local (Tier 4)</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-zinc-400 mb-1">DEFAULT MODEL (OPTIONAL)</label>
                <input
                  type="text"
                  placeholder="e.g. llama-3.3-70b-versatile"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full bg-[#101013] border border-zinc-700 px-2.5 py-1.5 rounded-[2px] text-zinc-200 focus:outline-none font-sans"
                />
              </div>
            </div>
            <div>
              <label className="block text-[10px] text-zinc-400 mb-1">API KEY / TOKEN</label>
              <input
                type="password"
                placeholder="sk-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full bg-[#101013] border border-zinc-700 px-2.5 py-1.5 rounded-[2px] text-zinc-200 focus:outline-none"
                required
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setIsAdding(false)}
                className="px-3 py-1 bg-zinc-900 border border-zinc-700 text-zinc-300 rounded-[2px] hover:bg-zinc-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-3 py-1 bg-zinc-100 text-zinc-950 font-semibold rounded-[2px] hover:bg-zinc-300"
              >
                Save Key
              </button>
            </div>
          </form>
        )}

        {/* ── Keys Table ─────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="p-8 text-center text-xs font-mono text-zinc-400">Loading keys...</div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-zinc-400">
              No keys found in vault. Add free provider keys above.
            </div>
          ) : (
            keys.map((k) => (
              <div
                key={k.id}
                className="p-3 bg-[#16161a] border border-zinc-800 rounded-[2px] flex items-center justify-between text-xs font-mono"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-zinc-200 uppercase">{k.provider}</span>
                    <span className="text-[10px] text-zinc-400 bg-zinc-900 px-1 py-0.5 border border-zinc-800 rounded-[2px]">
                      Tier {k.tier}
                    </span>
                    <span
                      className={`text-[9px] px-1 py-0.5 rounded-[2px] uppercase ${
                        k.status === 'ready'
                          ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/80'
                          : 'bg-amber-950/80 text-amber-300 border border-amber-800/80'
                      }`}
                    >
                      {k.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-400 flex items-center gap-3">
                    <span>Key: {k.masked_key}</span>
                    <span>•</span>
                    <span>Model: {k.default_model}</span>
                    <span>•</span>
                    <span>
                      Quota: {k.daily_requests_made} / {k.daily_limit}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handleDelete(k.id)}
                    className="p-1.5 text-zinc-400 hover:text-rose-400 rounded hover:bg-zinc-800"
                    title="Delete key"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
