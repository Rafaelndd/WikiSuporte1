/**
 * WikiSuporte 2.0 — Sidebar Component
 * Renderiza dinamicamente o menu lateral com base no role do usuário.
 */
const Sidebar = {
    menuItems: [
        { route: '/dashboard',     label: 'Dashboard',            icon: '📊', roles: null },
        { route: '/tarefas',       label: 'Tarefas',              icon: '✅', roles: null },
        { route: '/crm',           label: 'CRM / Tec. Consultor', icon: '🤝', roles: null },
        { route: '/suporte',       label: 'Suporte',              icon: '🎧', roles: null },
        { route: '/configuracoes', label: 'Configurações',        icon: '⚙️', roles: ['ceo', 'admin', 'gestor'] },
    ],

    render() {
        const user = Auth.getCurrentUser();
        const nav = document.getElementById('sidebar-nav');
        if (!nav) return;

        const items = this.menuItems.filter(item =>
            !item.roles || (user && item.roles.includes(user.role))
        );

        nav.innerHTML = `
            <div class="nav-section">
                <div class="nav-section-title">Menu Principal</div>
                ${items.map(item => `
                    <a class="nav-item" data-route="${item.route}" href="#${item.route}">
                        <span class="nav-icon">${item.icon}</span>
                        <span class="nav-label">${item.label}</span>
                    </a>
                `).join('')}
            </div>
        `;

        // Atualizar informações do usuário no footer
        if (user) {
            const initials = user.nome
                .split(' ')
                .slice(0, 2)
                .map(n => n[0])
                .join('')
                .toUpperCase();

            document.getElementById('user-info').innerHTML = `
                <div class="user-avatar">${initials}</div>
                <div class="user-details">
                    <div class="user-name">${user.nome}</div>
                    <div class="user-role">${user.role || 'Usuário'}</div>
                </div>
            `;
        }

        // Marcar item ativo
        const current = window.location.hash.replace('#', '') || '/dashboard';
        nav.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.route === current);
        });
    },
};
