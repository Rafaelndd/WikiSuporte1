/**
 * WikiSuporte 2.0 — Modal Component
 * Modal reutilizável com suporte a conteúdo dinâmico e callbacks.
 */
const Modal = {
    _overlay: null,
    _container: null,

    _init() {
        if (!this._overlay) {
            this._overlay = document.getElementById('modal-overlay');
            this._container = document.getElementById('modal-container');

            // Fechar ao clicar no overlay
            this._overlay.addEventListener('click', (e) => {
                if (e.target === this._overlay) this.close();
            });

            // Fechar com Escape
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') this.close();
            });
        }
    },

    /**
     * Abre o modal.
     * @param {Object} options
     * @param {string} options.title - Título do modal
     * @param {string} options.body - HTML do corpo do modal
     * @param {Array} options.actions - [{label, class, onClick}]
     */
    open({ title = '', body = '', actions = [] } = {}) {
        this._init();

        const actionsHtml = actions.map(a =>
            `<button class="btn ${a.class || 'btn-secondary'}" data-action="${a.label}">${a.label}</button>`
        ).join('');

        this._container.innerHTML = `
            <div class="modal-header">
                <h3>${title}</h3>
                <button class="modal-close" onclick="Modal.close()">✕</button>
            </div>
            <div class="modal-body">${body}</div>
            ${actions.length ? `<div class="modal-footer">${actionsHtml}</div>` : ''}
        `;

        // Vincular callbacks das ações
        actions.forEach(action => {
            const btn = this._container.querySelector(`[data-action="${action.label}"]`);
            if (btn && action.onClick) btn.addEventListener('click', () => action.onClick(btn));
        });

        this._overlay.classList.remove('hidden');
        this._container.querySelector('input, select, textarea')?.focus();
    },

    close() {
        this._init();
        this._overlay.classList.add('hidden');
        this._container.innerHTML = '';
    },

    confirm(message, onConfirm) {
        this.open({
            title: 'Confirmação',
            body: `<p>${message}</p>`,
            actions: [
                {
                    label: 'Cancelar',
                    class: 'btn-secondary',
                    onClick: () => this.close(),
                },
                {
                    label: 'Confirmar',
                    class: 'btn-danger',
                    onClick: () => { this.close(); onConfirm(); },
                },
            ],
        });
    },
};
