/**
 * WikiSuporte 2.0 — Kanban Component
 * Board Kanban com drag-and-drop usando a HTML5 Drag and Drop API.
 */
const Kanban = {
    /**
     * Renderiza o board no elemento container.
     * @param {HTMLElement} container - Elemento pai onde o board será inserido.
     * @param {Array} columns - [{id, nome, cor, tarefas: [...]}]
     * @param {Function} onMove - Callback chamado ao mover um card: (tarefaId, novoStatusId)
     */
    render(container, columns, onMove) {
        container.innerHTML = '';
        const board = document.createElement('div');
        board.className = 'kanban-board';

        columns.forEach(column => {
            const col = this._createColumn(column, onMove);
            board.appendChild(col);
        });

        container.appendChild(board);
    },

    _createColumn(column, onMove) {
        const col = document.createElement('div');
        col.className = 'kanban-column';
        col.dataset.statusId = column.id;

        const count = column.tarefas ? column.tarefas.length : 0;

        col.innerHTML = `
            <div class="kanban-column-header">
                <div class="kanban-column-title">
                    <span class="kanban-status-dot" style="background:${column.cor || '#9CA3AF'}"></span>
                    ${column.nome}
                </div>
                <div class="flex items-center gap-2">
                    <span class="kanban-count">${count}</span>
                    <button class="kanban-add-btn" title="Adicionar tarefa" data-status-id="${column.id}">+</button>
                </div>
            </div>
            <div class="kanban-cards" data-status-id="${column.id}"></div>
        `;

        const cardsContainer = col.querySelector('.kanban-cards');
        this._setupDropZone(cardsContainer, onMove);

        if (column.tarefas) {
            column.tarefas.forEach(tarefa => {
                cardsContainer.appendChild(this._createCard(tarefa));
            });
        }

        return col;
    },

    _createCard(tarefa) {
        const card = document.createElement('div');
        card.className = 'kanban-card';
        card.draggable = true;
        card.dataset.tarefaId = tarefa.id;

        const dueDate = tarefa.data_vencimento
            ? formatDate(tarefa.data_vencimento)
            : '';
        const isOverdue = tarefa.data_vencimento
            && new Date(tarefa.data_vencimento) < new Date()
            && !tarefa.concluida;

        card.innerHTML = `
            <div class="card-priority-bar ${tarefa.prioridade || 'normal'}"></div>
            <div class="card-title">${escapeHtml(tarefa.titulo)}</div>
            <div class="card-meta">
                <span class="card-due-date ${isOverdue ? 'overdue' : ''}">
                    ${dueDate ? `📅 ${dueDate}` : ''}
                </span>
                <div class="card-assignees" id="assignees-${tarefa.id}"></div>
            </div>
        `;

        this._setupDrag(card);
        return card;
    },

    _setupDrag(card) {
        card.addEventListener('dragstart', (e) => {
            card.classList.add('dragging');
            e.dataTransfer.setData('text/plain', card.dataset.tarefaId);
            e.dataTransfer.effectAllowed = 'move';
        });
        card.addEventListener('dragend', () => {
            card.classList.remove('dragging');
            document.querySelectorAll('.kanban-cards').forEach(el => el.classList.remove('drag-over'));
        });
    },

    _setupDropZone(container, onMove) {
        container.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            container.classList.add('drag-over');
        });
        container.addEventListener('dragleave', () => {
            container.classList.remove('drag-over');
        });
        container.addEventListener('drop', (e) => {
            e.preventDefault();
            container.classList.remove('drag-over');
            const tarefaId = parseInt(e.dataTransfer.getData('text/plain'));
            const novoStatusId = parseInt(container.dataset.statusId);
            if (tarefaId && novoStatusId && onMove) {
                onMove(tarefaId, novoStatusId);
            }
        });
    },
};

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
