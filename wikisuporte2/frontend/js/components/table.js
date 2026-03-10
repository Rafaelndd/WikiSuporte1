/**
 * WikiSuporte 2.0 — Table Component
 * Tabela genérica com suporte a ordenação e filtragem.
 */
const Table = {
    /**
     * Renderiza uma tabela no container especificado.
     * @param {HTMLElement} container
     * @param {Object} options
     * @param {Array} options.columns - [{key, label, render?}]
     * @param {Array} options.data    - Array de objetos
     * @param {Array} options.actions - [{label, class, onClick}] para coluna de ações
     */
    render(container, { columns = [], data = [], actions = [] } = {}) {
        if (!data.length) {
            container.innerHTML = `
                <div class="loading-spinner" style="padding: var(--space-8);">
                    Nenhum registro encontrado.
                </div>`;
            return;
        }

        const headerCols = columns.map(col =>
            `<th data-key="${col.key}">${col.label} <span class="sort-icon"></span></th>`
        ).join('');

        const actionsHeader = actions.length ? '<th>Ações</th>' : '';

        const rows = data.map(row => {
            const cells = columns.map(col => {
                const value = col.render ? col.render(row) : (row[col.key] ?? '—');
                return `<td>${value}</td>`;
            }).join('');

            const actionCells = actions.length ? `
                <td>
                    <div class="flex gap-2">
                        ${actions.map(a =>
                            `<button class="btn btn-sm ${a.class || 'btn-secondary'}" data-row-id="${row.id}">${a.label}</button>`
                        ).join('')}
                    </div>
                </td>` : '';

            return `<tr>${cells}${actionCells}</tr>`;
        }).join('');

        container.innerHTML = `
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>${headerCols}${actionsHeader}</tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;

        // Vincular ações
        actions.forEach(action => {
            container.querySelectorAll(`button[data-row-id]`).forEach(btn => {
                if (btn.textContent.trim() === action.label) {
                    btn.addEventListener('click', () => {
                        const rowId = parseInt(btn.dataset.rowId);
                        const row = data.find(r => r.id === rowId);
                        if (row) action.onClick(row, btn);
                    });
                }
            });
        });

        // Ordenação por coluna
        this._setupSort(container, data, columns, actions);
    },

    _setupSort(container, data, columns, actions) {
        let sortKey = null;
        let sortAsc = true;

        container.querySelectorAll('thead th[data-key]').forEach(th => {
            th.style.cursor = 'pointer';
            th.addEventListener('click', () => {
                const key = th.dataset.key;
                if (sortKey === key) {
                    sortAsc = !sortAsc;
                } else {
                    sortKey = key;
                    sortAsc = true;
                }

                const sorted = [...data].sort((a, b) => {
                    const va = a[key] ?? '';
                    const vb = b[key] ?? '';
                    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
                    return sortAsc ? cmp : -cmp;
                });

                // Re-renderizar
                this.render(container, { columns, data: sorted, actions });
            });
        });
    },
};
