/**
 * WikiSuporte 2.0 — Dashboard Page
 */
const PageDashboard = {
    async render(container) {
        container.innerHTML = `
            <div class="kpi-grid" id="kpi-grid">
                <div class="kpi-card"><div class="kpi-label">Carregando...</div></div>
            </div>
            <div class="dashboard-grid">
                <div class="card" style="grid-column: span 2;">
                    <div class="card-header">
                        <span class="card-title">Atendimentos por Analista</span>
                    </div>
                    <div id="chart-atendimentos"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Chamados por Status</span>
                    </div>
                    <div id="chart-chamados"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Prospecções por Status</span>
                    </div>
                    <div id="chart-prospecções"></div>
                </div>
            </div>
        `;

        try {
            const [resumo, atendPorAnalista, chamadosPorStatus, prospPorStatus] = await Promise.all([
                API.get('/api/dashboards/resumo'),
                API.get('/api/dashboards/atendimentos-por-analista'),
                API.get('/api/dashboards/chamados-por-status'),
                API.get('/api/dashboards/prospecções-por-status'),
            ]);

            this._renderKPIs(resumo);
            this._renderBarChart('chart-atendimentos', atendPorAnalista, 'nome', 'total');
            this._renderBarChart('chart-chamados', chamadosPorStatus, 'status', 'total');
            this._renderBarChart('chart-prospecções', prospPorStatus, 'status', 'total');
        } catch (err) {
            container.innerHTML += `<div class="loading-spinner">Erro ao carregar dashboard: ${err.message}</div>`;
        }
    },

    _renderKPIs(resumo) {
        const grid = document.getElementById('kpi-grid');
        grid.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-label">Total de Atendimentos</div>
                <div class="kpi-value">${resumo.total_atendimentos ?? 0}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Chamados Abertos</div>
                <div class="kpi-value">${resumo.chamados_abertos ?? 0}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Tarefas Pendentes</div>
                <div class="kpi-value">${resumo.tarefas_pendentes ?? 0}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Prospecções Ativas</div>
                <div class="kpi-value">${resumo.prospecções_ativas ?? 0}</div>
            </div>
        `;
    },

    _renderBarChart(containerId, data, labelKey, valueKey) {
        const container = document.getElementById(containerId);
        if (!container || !data.length) {
            if (container) container.innerHTML = '<div class="text-muted text-sm" style="padding:1rem">Sem dados</div>';
            return;
        }

        const max = Math.max(...data.map(d => d[valueKey] || 0)) || 1;

        container.innerHTML = `
            <div class="bar-chart">
                ${data.map(row => `
                    <div class="bar-row">
                        <span class="bar-label">${row[labelKey] || '—'}</span>
                        <div class="bar-track">
                            <div class="bar-fill" style="width:${Math.round((row[valueKey] / max) * 100)}%"></div>
                        </div>
                        <span class="bar-value">${row[valueKey]}</span>
                    </div>
                `).join('')}
            </div>
        `;
    },
};
