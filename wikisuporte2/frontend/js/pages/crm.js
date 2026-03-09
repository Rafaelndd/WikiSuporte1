/**
 * WikiSuporte 2.0 — CRM Page
 * Clientes, prospecções (com alerta de duplicidade) e pedidos de venda.
 */
const PageCRM = {
    _clientes: [],
    _prospecções: [],
    _pedidos: [],

    async render(container) {
        container.innerHTML = `
            <div class="tabs">
                <button class="tab-btn active" onclick="PageCRM.switchTab('clientes', this)">👥 Clientes</button>
                <button class="tab-btn" onclick="PageCRM.switchTab('prospecções', this)">📈 Prospecções</button>
                <button class="tab-btn" onclick="PageCRM.switchTab('pedidos', this)">🛒 Pedidos de Venda</button>
            </div>
            <div id="crm-tab-content"></div>
        `;

        await this.loadClientes();
        this.switchTab('clientes');
    },

    async loadClientes() {
        try {
            this._clientes = await API.get('/api/crm/clientes') || [];
        } catch (_) { this._clientes = []; }
    },

    async loadProspecções() {
        try {
            this._prospecções = await API.get('/api/crm/prospecções') || [];
        } catch (_) { this._prospecções = []; }
    },

    async loadPedidos() {
        try {
            this._pedidos = await API.get('/api/crm/pedidos') || [];
        } catch (_) { this._pedidos = []; }
    },

    switchTab(tab, btn) {
        if (btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
        const content = document.getElementById('crm-tab-content');
        if (!content) return;

        if (tab === 'clientes')    this._renderClientes(content);
        if (tab === 'prospecções') this._renderProspecções(content);
        if (tab === 'pedidos')     this._renderPedidos(content);
    },

    _renderClientes(container) {
        container.innerHTML = `
            <div class="client-list-header">
                <div class="search-input-wrapper">
                    <span class="search-icon">🔍</span>
                    <input type="text" placeholder="Buscar por nome ou CNPJ..." id="busca-cliente"
                           oninput="PageCRM._filterClientes(this.value)">
                </div>
                <button class="btn btn-primary" onclick="PageCRM.openCreateClienteModal()">+ Novo Cliente</button>
            </div>
            <div id="clientes-table"></div>
        `;
        this._renderClientesTable(this._clientes);
    },

    _filterClientes(busca) {
        const filtered = this._clientes.filter(c =>
            c.razao_social?.toLowerCase().includes(busca.toLowerCase()) ||
            c.cnpj?.includes(busca)
        );
        this._renderClientesTable(filtered);
    },

    _renderClientesTable(data) {
        const container = document.getElementById('clientes-table');
        if (!container) return;
        Table.render(container, {
            columns: [
                { key: 'razao_social', label: 'Razão Social' },
                { key: 'cnpj',         label: 'CNPJ' },
                { key: 'telefone',     label: 'Telefone' },
                { key: 'cidade',       label: 'Cidade/UF', render: r => r.cidade ? `${r.cidade}/${r.estado || ''}` : '—' },
            ],
            data,
            actions: [
                { label: 'Prospectar', class: 'btn-primary', onClick: (row) => this.openProspectarModal(row) },
                { label: 'Editar',     class: 'btn-secondary', onClick: (row) => this.openEditClienteModal(row) },
            ],
        });
    },

    async _renderProspecções(container) {
        await this.loadProspecções();
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageCRM.openProspectarModal()">+ Nova Prospecção</button>
            </div>
            <div id="prospecções-table"></div>
        `;
        Table.render(document.getElementById('prospecções-table'), {
            columns: [
                { key: 'cliente_id', label: 'Cliente', render: r => {
                    const c = this._clientes.find(c => c.id === r.cliente_id);
                    return c ? c.razao_social : `#${r.cliente_id}`;
                }},
                { key: 'status',      label: 'Status', render: r => `<span class="badge badge-primary">${r.status}</span>` },
                { key: 'data_contato', label: 'Último Contato', render: r => formatDate(r.data_contato) },
                { key: 'proximo_contato', label: 'Próximo Contato', render: r => formatDate(r.proximo_contato) },
            ],
            data: this._prospecções,
            actions: [
                { label: 'Editar', class: 'btn-secondary', onClick: (row) => this.openEditProspeccaoModal(row) },
            ],
        });
    },

    async _renderPedidos(container) {
        await this.loadPedidos();
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageCRM.openCreatePedidoModal()">+ Novo Pedido</button>
            </div>
            <div id="pedidos-table"></div>
        `;
        Table.render(document.getElementById('pedidos-table'), {
            columns: [
                { key: 'id',          label: '#' },
                { key: 'cliente_id',  label: 'Cliente', render: r => {
                    const c = this._clientes.find(c => c.id === r.cliente_id);
                    return c ? c.razao_social : `#${r.cliente_id}`;
                }},
                { key: 'status',      label: 'Status', render: r => `<span class="badge badge-gray">${r.status}</span>` },
                { key: 'valor_total', label: 'Valor Total', render: r => formatCurrency(r.valor_total) },
                { key: 'criado_em',   label: 'Data', render: r => formatDate(r.criado_em) },
            ],
            data: this._pedidos,
        });
    },

    openCreateClienteModal() {
        Modal.open({
            title: 'Novo Cliente',
            body: `
                <div class="form-group">
                    <label class="form-label">Razão Social *</label>
                    <input type="text" id="c-razao" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">CNPJ</label>
                    <input type="text" id="c-cnpj" class="form-input" placeholder="00.000.000/0000-00">
                </div>
                <div class="form-group">
                    <label class="form-label">Telefone</label>
                    <input type="text" id="c-tel" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">E-mail</label>
                    <input type="email" id="c-email" class="form-input">
                </div>
                <div style="display:grid;grid-template-columns:1fr 80px;gap:var(--space-3);">
                    <div class="form-group">
                        <label class="form-label">Cidade</label>
                        <input type="text" id="c-cidade" class="form-input">
                    </div>
                    <div class="form-group">
                        <label class="form-label">UF</label>
                        <input type="text" id="c-estado" class="form-input" maxlength="2">
                    </div>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Salvar',   class: 'btn-primary',   onClick: () => this._createCliente() },
            ],
        });
    },

    async _createCliente() {
        const razao = document.getElementById('c-razao').value.trim();
        if (!razao) { showToast('Razão social é obrigatória', 'error'); return; }
        try {
            const novo = await API.post('/api/crm/clientes', {
                razao_social: razao,
                cnpj: document.getElementById('c-cnpj').value || null,
                telefone: document.getElementById('c-tel').value || null,
                email: document.getElementById('c-email').value || null,
                cidade: document.getElementById('c-cidade').value || null,
                estado: document.getElementById('c-estado').value || null,
            });
            this._clientes.unshift(novo);
            Modal.close();
            showToast('Cliente cadastrado!', 'success');
            document.querySelector('[onclick*="clientes"]')?.click();
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openProspectarModal(cliente) {
        const clienteOptions = this._clientes.map(c =>
            `<option value="${c.id}" ${cliente && c.id === cliente.id ? 'selected' : ''}>${c.razao_social}</option>`
        ).join('');

        Modal.open({
            title: 'Nova Prospecção',
            body: `
                <div class="form-group">
                    <label class="form-label">Cliente *</label>
                    <select id="p-cliente" class="form-select">${clienteOptions}</select>
                </div>
                <div class="form-group">
                    <label class="form-label">Status</label>
                    <select id="p-status" class="form-select">
                        <option value="prospectando">Prospectando</option>
                        <option value="em_negociacao">Em Negociação</option>
                        <option value="convertido">Convertido</option>
                        <option value="perdido">Perdido</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Próximo Contato</label>
                    <input type="datetime-local" id="p-proximo" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Observações</label>
                    <textarea id="p-desc" class="form-textarea"></textarea>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Salvar',   class: 'btn-primary',   onClick: () => this._createProspeccao() },
            ],
        });
    },

    async _createProspeccao() {
        const clienteId = parseInt(document.getElementById('p-cliente').value);
        try {
            const nova = await API.post('/api/crm/prospecções', {
                cliente_id: clienteId,
                status: document.getElementById('p-status').value,
                proximo_contato: document.getElementById('p-proximo').value || null,
                descricao: document.getElementById('p-desc').value || null,
            });
            this._prospecções.unshift(nova);
            Modal.close();
            showToast('Prospecção registrada!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openCreatePedidoModal() {
        const clienteOptions = this._clientes.map(c =>
            `<option value="${c.id}">${c.razao_social}</option>`
        ).join('');
        Modal.open({
            title: 'Novo Pedido de Venda',
            body: `
                <div class="form-group">
                    <label class="form-label">Cliente *</label>
                    <select id="ped-cliente" class="form-select">${clienteOptions}</select>
                </div>
                <div class="form-group">
                    <label class="form-label">Observações</label>
                    <textarea id="ped-obs" class="form-textarea"></textarea>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Criar',    class: 'btn-primary',   onClick: () => this._createPedido() },
            ],
        });
    },

    async _createPedido() {
        const clienteId = parseInt(document.getElementById('ped-cliente').value);
        try {
            const novo = await API.post('/api/crm/pedidos', {
                cliente_id: clienteId,
                observacoes: document.getElementById('ped-obs').value || null,
                itens: [],
            });
            this._pedidos.unshift(novo);
            Modal.close();
            showToast('Pedido criado!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },
};
