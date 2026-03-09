/**
 * WikiSuporte 2.0 — SPA Router
 * Roteamento baseado em hash (#/rota) com guard de autenticação.
 */

const ROUTES = {
    '/dashboard':     { page: PageDashboard,      title: 'Dashboard',           icon: '📊' },
    '/tarefas':       { page: PageTarefas,         title: 'Tarefas',             icon: '✅' },
    '/crm':           { page: PageCRM,             title: 'CRM / Técnico Consultor', icon: '🤝' },
    '/suporte':       { page: PageSuporte,         title: 'Suporte',             icon: '🎧' },
    '/configuracoes': { page: PageConfiguracoes,   title: 'Configurações',       icon: '⚙️' },
};

const Router = {
    current: null,

    init() {
        window.addEventListener('hashchange', () => this.navigate());
        this.navigate();
    },

    navigate() {
        if (!Auth.guard()) return;

        const hash = window.location.hash.replace('#', '') || '/dashboard';
        const route = ROUTES[hash] || ROUTES['/dashboard'];

        document.getElementById('page-title').textContent = route.title;
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.route === hash);
        });

        const content = document.getElementById('page-content');
        content.innerHTML = '<div class="loading-spinner">Carregando...</div>';

        this.current = hash;

        // Renderizar a página
        try {
            route.page.render(content);
        } catch (err) {
            content.innerHTML = `<div class="loading-spinner">Erro ao carregar a página: ${err.message}</div>`;
            console.error(err);
        }
    },

    go(path) {
        window.location.hash = path;
    },
};

// --- Utilitários de UI globais ---

function showToast(message, type = 'default', duration = 3000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

// --- Inicialização --- 
document.addEventListener('DOMContentLoaded', async () => {
    if (!Auth.guard()) return;

    // Buscar dados do usuário
    await Auth.fetchCurrentUser();

    // Renderizar sidebar
    Sidebar.render();

    // Iniciar roteador
    Router.init();

    // Toggle da sidebar
    document.getElementById('sidebar-toggle').addEventListener('click', () => {
        document.getElementById('app').classList.toggle('sidebar-collapsed');
    });
});
