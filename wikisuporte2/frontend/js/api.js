/**
 * WikiSuporte 2.0 — API Wrapper
 * Centraliza todas as requisições ao backend FastAPI.
 * Injeta JWT automaticamente e renova o token em caso de 401.
 */
const API_BASE = window.API_BASE || 'http://localhost:8000';

const API = {
    _getHeaders(extra = {}) {
        const token = localStorage.getItem('access_token');
        const headers = { 'Content-Type': 'application/json', ...extra };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return headers;
    },

    async _request(method, path, body = null, retry = true) {
        const options = {
            method,
            headers: this._getHeaders(),
        };
        if (body !== null) options.body = JSON.stringify(body);

        const response = await fetch(`${API_BASE}${path}`, options);

        // Token expirado — tenta renovar uma vez
        if (response.status === 401 && retry) {
            const refreshed = await this._tryRefresh();
            if (refreshed) return this._request(method, path, body, false);
            // Refresh falhou — redireciona para login
            Auth.logout();
            return;
        }

        if (!response.ok) {
            let detail = `Erro ${response.status}`;
            try {
                const err = await response.json();
                detail = err.detail || detail;
            } catch (_) {}
            throw new Error(detail);
        }

        if (response.status === 204) return null;

        return response.json();
    },

    async _tryRefresh() {
        const refresh = localStorage.getItem('refresh_token');
        if (!refresh) return false;
        try {
            const res = await fetch(`${API_BASE}/api/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refresh }),
            });
            if (!res.ok) return false;
            const data = await res.json();
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            return true;
        } catch (_) {
            return false;
        }
    },

    get(path)              { return this._request('GET',    path); },
    post(path, body)       { return this._request('POST',   path, body); },
    put(path, body)        { return this._request('PUT',    path, body); },
    patch(path, body)      { return this._request('PATCH',  path, body); },
    delete(path)           { return this._request('DELETE', path); },
};
