/**
 * WikiSuporte 2.0 — Auth
 * Gerencia login, logout, tokens e dados do usuário atual.
 */
const Auth = {
    _currentUser: null,

    isLoggedIn() {
        return !!localStorage.getItem('access_token');
    },

    getToken() {
        return localStorage.getItem('access_token');
    },

    saveTokens(access, refresh) {
        localStorage.setItem('access_token', access);
        localStorage.setItem('refresh_token', refresh);
    },

    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('current_user');
        this._currentUser = null;
    },

    logout() {
        this.clearTokens();
        window.location.href = 'login.html';
    },

    async fetchCurrentUser() {
        try {
            const user = await API.get('/api/auth/me');
            this._currentUser = user;
            localStorage.setItem('current_user', JSON.stringify(user));
            return user;
        } catch (_) {
            this.logout();
            return null;
        }
    },

    getCurrentUser() {
        if (this._currentUser) return this._currentUser;
        const stored = localStorage.getItem('current_user');
        if (stored) {
            try {
                this._currentUser = JSON.parse(stored);
                return this._currentUser;
            } catch (_) {}
        }
        return null;
    },

    hasRole(...roles) {
        const user = this.getCurrentUser();
        return user && roles.includes(user.role);
    },

    /** Inicia o guard de autenticação — redireciona para login se não logado */
    guard() {
        if (!this.isLoggedIn()) {
            window.location.href = 'login.html';
            return false;
        }
        return true;
    },
};

// Função global para o botão de logout no HTML
function logout() { Auth.logout(); }
