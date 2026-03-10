/**
 * WikiSuporte 2.0 — Configurações Page
 */
const PageConfiguracoes = {
    async render(container) {
        const user = Auth.getCurrentUser();
        if (!user || !['ceo', 'admin', 'gestor'].includes(user.role)) {
            container.innerHTML = `
                <div class="loading-spinner">
                    Você não tem permissão para acessar as configurações.
                </div>`;
            return;
        }

        container.innerHTML = `
            <div class="tabs">
                <button class="tab-btn active" onclick="PageConfiguracoes.switchTab('usuarios', this)">👤 Usuários</button>
                <button class="tab-btn" onclick="PageConfiguracoes.switchTab('setores', this)">🏢 Setores</button>
            </div>
            <div id="config-tab-content"></div>
        `;

        this.switchTab('usuarios');
    },

    switchTab(tab, btn) {
        if (btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
        const content = document.getElementById('config-tab-content');
        if (!content) return;
        if (tab === 'usuarios') this._renderUsuarios(content);
        if (tab === 'setores')  this._renderSetores(content);
    },

    async _renderUsuarios(container) {
        let usuarios = [];
        let roles = [];
        try {
            [usuarios, roles] = await Promise.all([
                API.get('/api/usuarios/'),
                API.get('/api/usuarios/roles/'),
            ]);
        } catch (_) {}

        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageConfiguracoes.openCreateUsuarioModal()">+ Novo Usuário</button>
            </div>
            <div id="usuarios-table"></div>
        `;

        Table.render(document.getElementById('usuarios-table'), {
            columns: [
                { key: 'nome',  label: 'Nome' },
                { key: 'email', label: 'E-mail' },
                { key: 'role',  label: 'Role', render: r => r.role ? `<span class="badge badge-primary">${r.role.nome}</span>` : '—' },
                { key: 'setor', label: 'Setor', render: r => r.setor?.nome || '—' },
                { key: 'ativo', label: 'Ativo', render: r => r.ativo
                    ? '<span class="badge badge-success">Sim</span>'
                    : '<span class="badge badge-danger">Não</span>' },
            ],
            data: usuarios,
            actions: [
                { label: 'Editar', class: 'btn-secondary', onClick: (row) => this.openEditUsuarioModal(row) },
            ],
        });
    },

    async _renderSetores(container) {
        let setores = [];
        try { setores = await API.get('/api/usuarios/setores/') || []; } catch (_) {}

        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageConfiguracoes.openCreateSetorModal()">+ Novo Setor</button>
            </div>
            <div id="setores-table"></div>
        `;

        Table.render(document.getElementById('setores-table'), {
            columns: [
                { key: 'nome',      label: 'Nome' },
                { key: 'descricao', label: 'Descrição' },
                { key: 'ativo',     label: 'Ativo', render: r => r.ativo
                    ? '<span class="badge badge-success">Sim</span>'
                    : '<span class="badge badge-danger">Não</span>' },
            ],
            data: setores,
        });
    },

    openCreateUsuarioModal() {
        Modal.open({
            title: 'Novo Usuário',
            body: `
                <div class="form-group">
                    <label class="form-label">Nome *</label>
                    <input type="text" id="u-nome" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">E-mail *</label>
                    <input type="email" id="u-email" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Senha *</label>
                    <input type="password" id="u-senha" class="form-input" required>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Criar',    class: 'btn-primary',   onClick: () => this._createUsuario() },
            ],
        });
    },

    async _createUsuario() {
        const nome  = document.getElementById('u-nome').value.trim();
        const email = document.getElementById('u-email').value.trim();
        const senha = document.getElementById('u-senha').value;
        if (!nome || !email || !senha) { showToast('Preencha todos os campos obrigatórios', 'error'); return; }
        try {
            await API.post('/api/usuarios/', { nome, email, senha });
            Modal.close();
            showToast('Usuário criado!', 'success');
            document.querySelector('[onclick*="usuarios"]')?.click();
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openCreateSetorModal() {
        Modal.open({
            title: 'Novo Setor',
            body: `
                <div class="form-group">
                    <label class="form-label">Nome *</label>
                    <input type="text" id="s-nome" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Descrição</label>
                    <textarea id="s-desc" class="form-textarea"></textarea>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Criar',    class: 'btn-primary',   onClick: () => this._createSetor() },
            ],
        });
    },

    async _createSetor() {
        const nome = document.getElementById('s-nome').value.trim();
        if (!nome) { showToast('Nome é obrigatório', 'error'); return; }
        try {
            await API.post('/api/usuarios/setores/', { nome, descricao: document.getElementById('s-desc').value || null });
            Modal.close();
            showToast('Setor criado!', 'success');
            document.querySelector('[onclick*="setores"]')?.click();
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },
};
