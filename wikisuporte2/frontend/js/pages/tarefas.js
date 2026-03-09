/**
 * WikiSuporte 2.0 — Tarefas Page
 * Alterna entre visão Lista e Kanban.
 */
const PageTarefas = {
    _view: 'lista',
    _tarefas: [],
    _statusList: [],

    async render(container) {
        container.innerHTML = `
            <div class="flex items-center gap-4 mb-4" style="justify-content: space-between;">
                <div class="view-toggle">
                    <button class="view-toggle-btn active" id="btn-lista" onclick="PageTarefas.setView('lista', this)">📋 Lista</button>
                    <button class="view-toggle-btn" id="btn-kanban" onclick="PageTarefas.setView('kanban', this)">🗂 Kanban</button>
                </div>
                <button class="btn btn-primary" onclick="PageTarefas.openCreateModal()">+ Nova Tarefa</button>
            </div>
            <div id="tarefas-content"></div>
        `;

        try {
            const [tarefas, espacos] = await Promise.all([
                API.get('/api/tarefas/?apenas_raiz=true'),
                API.get('/api/tarefas/espacos'),
            ]);
            this._tarefas = tarefas || [];

            if (espacos && espacos.length > 0) {
                const status = await API.get(`/api/tarefas/status?espaco_id=${espacos[0].id}`);
                this._statusList = status || [];
            }
        } catch (err) {
            this._tarefas = [];
        }

        this.setView(this._view);
    },

    setView(view, btn) {
        this._view = view;
        if (btn) {
            document.querySelectorAll('.view-toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }
        const content = document.getElementById('tarefas-content');
        if (!content) return;
        view === 'kanban' ? this._renderKanban(content) : this._renderLista(content);
    },

    _renderLista(container) {
        Table.render(container, {
            columns: [
                { key: 'titulo',     label: 'Título' },
                { key: 'prioridade', label: 'Prioridade', render: row => `<span class="priority-${row.prioridade}">${row.prioridade}</span>` },
                { key: 'data_vencimento', label: 'Vencimento', render: row => formatDate(row.data_vencimento) },
                { key: 'concluida',  label: 'Status', render: row => row.concluida
                    ? '<span class="badge badge-success">Concluída</span>'
                    : '<span class="badge badge-gray">Pendente</span>' },
            ],
            data: this._tarefas,
            actions: [
                { label: 'Editar', class: 'btn-secondary', onClick: (row) => this.openEditModal(row) },
                { label: 'Excluir', class: 'btn-danger',   onClick: (row) => this.deleteTarefa(row) },
            ],
        });
    },

    _renderKanban(container) {
        if (!this._statusList.length) {
            container.innerHTML = '<div class="loading-spinner">Configure um Espaço com status para usar o Kanban.</div>';
            return;
        }
        const columns = this._statusList.map(s => ({
            id: s.id,
            nome: s.nome,
            cor: s.cor,
            tarefas: this._tarefas.filter(t => t.status_id === s.id),
        }));
        Kanban.render(container, columns, (tarefaId, novoStatusId) => {
            this._moveCard(tarefaId, novoStatusId);
        });
    },

    async _moveCard(tarefaId, novoStatusId) {
        try {
            await API.put(`/api/tarefas/${tarefaId}`, { status_id: novoStatusId });
            const t = this._tarefas.find(t => t.id === tarefaId);
            if (t) t.status_id = novoStatusId;
            showToast('Tarefa movida!', 'success');
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openCreateModal() {
        Modal.open({
            title: 'Nova Tarefa',
            body: `
                <div class="form-group">
                    <label class="form-label">Título *</label>
                    <input type="text" id="t-titulo" class="form-input" placeholder="Título da tarefa" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Descrição</label>
                    <textarea id="t-desc" class="form-textarea" placeholder="Descrição opcional"></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Prioridade</label>
                    <select id="t-prioridade" class="form-select">
                        <option value="normal">Normal</option>
                        <option value="alta">Alta</option>
                        <option value="urgente">Urgente</option>
                        <option value="baixa">Baixa</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Vencimento</label>
                    <input type="datetime-local" id="t-vencimento" class="form-input">
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Criar', class: 'btn-primary', onClick: () => this._createTarefa() },
            ],
        });
    },

    async _createTarefa() {
        const titulo = document.getElementById('t-titulo').value.trim();
        if (!titulo) { showToast('Título é obrigatório', 'error'); return; }
        try {
            const nova = await API.post('/api/tarefas/', {
                titulo,
                descricao: document.getElementById('t-desc').value || null,
                prioridade: document.getElementById('t-prioridade').value,
                data_vencimento: document.getElementById('t-vencimento').value || null,
            });
            this._tarefas.unshift(nova);
            Modal.close();
            showToast('Tarefa criada!', 'success');
            this.setView(this._view);
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    openEditModal(tarefa) {
        const due = tarefa.data_vencimento
            ? new Date(tarefa.data_vencimento).toISOString().slice(0, 16)
            : '';
        Modal.open({
            title: 'Editar Tarefa',
            body: `
                <div class="form-group">
                    <label class="form-label">Título *</label>
                    <input type="text" id="t-titulo" class="form-input" value="${escapeHtml(tarefa.titulo)}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Prioridade</label>
                    <select id="t-prioridade" class="form-select">
                        ${['urgente','alta','normal','baixa'].map(p =>
                            `<option value="${p}" ${tarefa.prioridade === p ? 'selected' : ''}>${p}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Vencimento</label>
                    <input type="datetime-local" id="t-vencimento" class="form-input" value="${due}">
                </div>
                <div class="form-group">
                    <label class="form-label">Concluída</label>
                    <input type="checkbox" id="t-concluida" ${tarefa.concluida ? 'checked' : ''}>
                </div>
            `,
            actions: [
                { label: 'Cancelar', class: 'btn-secondary', onClick: () => Modal.close() },
                { label: 'Salvar', class: 'btn-primary', onClick: () => this._updateTarefa(tarefa.id) },
            ],
        });
    },

    async _updateTarefa(id) {
        try {
            const updated = await API.put(`/api/tarefas/${id}`, {
                titulo: document.getElementById('t-titulo').value,
                prioridade: document.getElementById('t-prioridade').value,
                data_vencimento: document.getElementById('t-vencimento').value || null,
                concluida: document.getElementById('t-concluida').checked,
            });
            const idx = this._tarefas.findIndex(t => t.id === id);
            if (idx !== -1) this._tarefas[idx] = updated;
            Modal.close();
            showToast('Tarefa atualizada!', 'success');
            this.setView(this._view);
        } catch (err) {
            showToast(`Erro: ${err.message}`, 'error');
        }
    },

    deleteTarefa(tarefa) {
        Modal.confirm(`Excluir a tarefa "${tarefa.titulo}"?`, async () => {
            try {
                await API.delete(`/api/tarefas/${tarefa.id}`);
                this._tarefas = this._tarefas.filter(t => t.id !== tarefa.id);
                showToast('Tarefa excluída!', 'success');
                this.setView(this._view);
            } catch (err) {
                showToast(`Erro: ${err.message}`, 'error');
            }
        });
    },
};
