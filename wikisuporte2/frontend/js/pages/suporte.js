/**
 * WikiSuporte 2.0 — Suporte Page
 * Atendimentos, chamados, plantões e importações.
 */
const PageSuporte = {
    _atendimentos: [],
    _chamados: [],

    async render(container) {
        container.innerHTML = `
            <div class="tabs">
                <button class="tab-btn active" onclick="PageSuporte.switchTab('atendimentos', this)">📞 Atendimentos</button>
                <button class="tab-btn" onclick="PageSuporte.switchTab('chamados', this)">🎫 Chamados</button>
                <button class="tab-btn" onclick="PageSuporte.switchTab('plantoes', this)">🌙 Plantões</button>
                <button class="tab-btn" onclick="PageSuporte.switchTab('importacoes', this)">📁 Importações</button>
            </div>
            <div id="suporte-tab-content"></div>
        `;
        await this.loadData();
        this.switchTab('atendimentos');
    },

    async loadData() {
        try {
            [this._atendimentos, this._chamados] = await Promise.all([
                API.get('/api/suporte/atendimentos'),
                API.get('/api/suporte/chamados'),
            ]);
        } catch (_) {
            this._atendimentos = [];
            this._chamados = [];
        }
    },

    switchTab(tab, btn) {
        if (btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
        const content = document.getElementById('suporte-tab-content');
        if (!content) return;

        const renders = {
            atendimentos: () => this._renderAtendimentos(content),
            chamados:     () => this._renderChamados(content),
            plantoes:     () => this._renderPlantoes(content),
            importacoes:  () => this._renderImportacoes(content),
        };
        renders[tab]?.();
    },

    _renderAtendimentos(container) {
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageSuporte.openRegistrarAtendimentoModal()">+ Registrar Atendimento</button>
            </div>
            <div id="atend-table"></div>
        `;
        Table.render(document.getElementById('atend-table'), {
            columns: [
                { key: 'data_atendimento', label: 'Data/Hora', render: r => formatDateTime(r.data_atendimento) },
                { key: 'cliente_nome',     label: 'Cliente' },
                { key: 'tipo',             label: 'Tipo', render: r => `<span class="badge badge-primary">${r.tipo}</span>` },
                { key: 'duracao_minutos',  label: 'Duração', render: r => r.duracao_minutos ? `${r.duracao_minutos} min` : '—' },
                { key: 'fonte',            label: 'Fonte', render: r => r.fonte || '—' },
            ],
            data: this._atendimentos,
        });
    },

    _renderChamados(container) {
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageSuporte.openNovoChamadoModal()">+ Abrir Chamado</button>
            </div>
            <div id="chamados-table"></div>
        `;
        Table.render(document.getElementById('chamados-table'), {
            columns: [
                { key: 'titulo',       label: 'Título' },
                { key: 'status',       label: 'Status', render: r => {
                    const cls = { aberto: 'danger', em_andamento: 'warning', resolvido: 'success', fechado: 'gray' }[r.status] || 'gray';
                    return `<span class="badge badge-${cls}">${r.status.replace('_', ' ')}</span>`;
                }},
                { key: 'prioridade',   label: 'Prioridade' },
                { key: 'data_abertura', label: 'Abertura', render: r => formatDate(r.data_abertura) },
            ],
            data: this._chamados,
            actions: [
                { label: 'Editar', class: 'btn-secondary', onClick: (row) => this.openEditChamadoModal(row) },
            ],
        });
    },

    async _renderPlantoes(container) {
        let plantoes = [];
        try { plantoes = await API.get('/api/suporte/plantoes') || []; } catch (_) {}
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageSuporte.openRegistrarPlantaoModal()">+ Registrar Plantão</button>
            </div>
            <div id="plantoes-table"></div>
        `;
        Table.render(document.getElementById('plantoes-table'), {
            columns: [
                { key: 'data_inicio', label: 'Início',    render: r => formatDateTime(r.data_inicio) },
                { key: 'data_fim',    label: 'Fim',       render: r => formatDateTime(r.data_fim) },
                { key: 'tipo',        label: 'Tipo' },
            ],
            data: plantoes,
        });
    },

    async _renderImportacoes(container) {
        let importacoes = [];
        try { importacoes = await API.get('/api/suporte/importacoes') || []; } catch (_) {}
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: flex-end;">
                <button class="btn btn-primary" onclick="PageSuporte.openImportacaoModal()">+ Nova Importação</button>
            </div>
            <div id="importacoes-table"></div>
        `;
        Table.render(document.getElementById('importacoes-table'), {
            columns: [
                { key: 'tipo',               label: 'Tipo' },
                { key: 'nome_arquivo',        label: 'Arquivo' },
                { key: 'status',              label: 'Status', render: r => {
                    const cls = { concluido: 'success', erro: 'danger', processando: 'warning', pendente: 'gray' }[r.status] || 'gray';
                    return `<span class="badge badge-${cls}">${r.status}</span>`;
                }},
                { key: 'registros_importados', label: 'Importados' },
                { key: 'registros_erro',        label: 'Erros' },
                { key: 'criado_em',             label: 'Data', render: r => formatDateTime(r.criado_em) },
            ],
            data: importacoes,
        });
    },

    openRegistrarAtendimentoModal() {
        Modal.open({
            title: 'Registrar Atendimento',
            body: `
                <div class="form-group">
                    <label class="form-label">Nome do Cliente</label>
                    <input type="text" id="a-cliente" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Tipo</label>
                    <select id="a-tipo" class="form-select">
                        <option value="telefone">Telefone</option>
                        <option value="email">E-mail</option>
                        <option value="chat">Chat</option>
                        <option value="presencial">Presencial</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Duração (minutos)</label>
                    <input type="number" id="a-duracao" class="form-input" min="1">
                </div>
                <div class="form-group">
                    <label class="form-label">Descrição / Resolução</label>
                    <textarea id="a-desc" class="form-textarea"></textarea>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Salvar',   class: 'btn-primary',   onClick: () => this._registrarAtendimento() },
            ],
        });
    },

    async _registrarAtendimento() {
        try {
            const novo = await API.post('/api/suporte/atendimentos', {
                cliente_nome: document.getElementById('a-cliente').value || null,
                tipo: document.getElementById('a-tipo').value,
                duracao_minutos: parseInt(document.getElementById('a-duracao').value) || null,
                descricao: document.getElementById('a-desc').value || null,
                fonte: 'manual',
            });
            this._atendimentos.unshift(novo);
            Modal.close();
            showToast('Atendimento registrado!', 'success');
            document.querySelector('[onclick*="atendimentos"]')?.click();
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openNovoChamadoModal() {
        Modal.open({
            title: 'Abrir Chamado',
            body: `
                <div class="form-group">
                    <label class="form-label">Título *</label>
                    <input type="text" id="ch-titulo" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Prioridade</label>
                    <select id="ch-prioridade" class="form-select">
                        <option value="normal">Normal</option>
                        <option value="alta">Alta</option>
                        <option value="urgente">Urgente</option>
                        <option value="baixa">Baixa</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Descrição</label>
                    <textarea id="ch-desc" class="form-textarea"></textarea>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Abrir',    class: 'btn-primary',   onClick: () => this._criarChamado() },
            ],
        });
    },

    async _criarChamado() {
        const titulo = document.getElementById('ch-titulo').value.trim();
        if (!titulo) { showToast('Título é obrigatório', 'error'); return; }
        try {
            const novo = await API.post('/api/suporte/chamados', {
                titulo,
                prioridade: document.getElementById('ch-prioridade').value,
                descricao: document.getElementById('ch-desc').value || null,
            });
            this._chamados.unshift(novo);
            Modal.close();
            showToast('Chamado aberto!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openRegistrarPlantaoModal() {
        Modal.open({
            title: 'Registrar Plantão',
            body: `
                <div class="form-group">
                    <label class="form-label">Início *</label>
                    <input type="datetime-local" id="pl-inicio" class="form-input" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Fim</label>
                    <input type="datetime-local" id="pl-fim" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Tipo</label>
                    <select id="pl-tipo" class="form-select">
                        <option value="diurno">Diurno</option>
                        <option value="noturno">Noturno</option>
                        <option value="fim_de_semana">Fim de semana</option>
                    </select>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Salvar',   class: 'btn-primary',   onClick: () => this._registrarPlantao() },
            ],
        });
    },

    async _registrarPlantao() {
        const inicio = document.getElementById('pl-inicio').value;
        if (!inicio) { showToast('Data de início é obrigatória', 'error'); return; }
        try {
            await API.post('/api/suporte/plantoes', {
                data_inicio: inicio,
                data_fim: document.getElementById('pl-fim').value || null,
                tipo: document.getElementById('pl-tipo').value,
            });
            Modal.close();
            showToast('Plantão registrado!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openImportacaoModal() {
        Modal.open({
            title: 'Iniciar Importação',
            body: `
                <div class="form-group">
                    <label class="form-label">Tipo de Importação</label>
                    <select id="imp-tipo" class="form-select">
                        <option value="multi360_csv">Multi360 (CSV)</option>
                        <option value="goto_api">GoTo Connect (API)</option>
                        <option value="chamados_bot">Chamados (Bot)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Nome do Arquivo (opcional)</label>
                    <input type="text" id="imp-arquivo" class="form-input" placeholder="nome_arquivo.csv">
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Iniciar',  class: 'btn-primary',   onClick: () => this._iniciarImportacao() },
            ],
        });
    },

    async _iniciarImportacao() {
        try {
            await API.post('/api/suporte/importacoes', {
                tipo: document.getElementById('imp-tipo').value,
                nome_arquivo: document.getElementById('imp-arquivo').value || null,
            });
            Modal.close();
            showToast('Importação iniciada!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },
};
