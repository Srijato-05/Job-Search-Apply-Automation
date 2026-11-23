import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, apiFetch, getLocalToken, setLocalToken } from '../api/client';

function makeResponse(body: unknown, status = 200, isJson = true) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (!isJson) throw new Error('invalid json');
      return body;
    },
    blob: async () => new Blob(['zip-bytes'], { type: 'application/zip' }),
  } as Response);
}

describe('API client & token management', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = undefined;
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('resolves token from window global or localStorage via setLocalToken', () => {
    expect(getLocalToken()).toBe('');

    setLocalToken('  secret-token-123  ');
    expect(window.__JOB_AUTOMATION_TOKEN__).toBe('secret-token-123');
    expect(getLocalToken()).toBe('secret-token-123');

    window.__JOB_AUTOMATION_TOKEN__ = undefined;
    expect(getLocalToken()).toBe('secret-token-123');
  });

  it('injects X-Local-Token and Content-Type for JSON, omits Content-Type for FormData, handles 204', async () => {
    setLocalToken('tok-abc');
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      const hdrs = init?.headers as Headers;
      expect(hdrs.get('X-Local-Token')).toBe('tok-abc');
      return makeResponse(null, 204);
    });
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('/api/v1/test', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    const firstHeaders = (fetchMock.mock.calls[0][1] as RequestInit).headers as Headers;
    expect(firstHeaders.get('Content-Type')).toBe('application/json');

    const fd = new FormData();
    fd.append('k', 'v');
    await apiFetch('/api/v1/upload', { method: 'POST', body: fd });
    const secondHeaders = (fetchMock.mock.calls[1][1] as RequestInit).headers as Headers;
    expect(secondHeaders.has('Content-Type')).toBe(false);
  });

  it('throws ApiError with JSON detail on 401/409 and fallback HTTP status on non-JSON 500', async () => {
    setLocalToken('tok-abc');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(makeResponse({ detail: 'Invalid or missing X-Local-Token' }, 401))
        .mockResolvedValueOnce(makeResponse({ detail: 'A collection sweep is already in progress.' }, 409))
        .mockResolvedValueOnce(makeResponse(null, 500, false)),
    );

    await expect(api.getVault()).rejects.toMatchObject({
      status: 401,
      message: 'Invalid or missing X-Local-Token',
    });
    await expect(api.runCollectors('ats')).rejects.toMatchObject({
      status: 409,
      message: 'A collection sweep is already in progress.',
    });
    try {
      await api.getAnalytics();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).message).toBe('HTTP 500');
    }
  });

  it('downloadBackupZip attaches token and rejects on HTTP failure', async () => {
    setLocalToken('tok-zip');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(makeResponse(null, 200))
        .mockResolvedValueOnce(makeResponse(null, 500)),
    );

    const blob = await api.downloadBackupZip();
    expect(blob).toBeInstanceOf(Blob);

    await expect(api.downloadBackupZip()).rejects.toMatchObject({
      status: 500,
    });
  });
});

