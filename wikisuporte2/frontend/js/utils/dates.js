/**
 * WikiSuporte 2.0 — Helpers de formatação de datas
 */

/**
 * Formata uma string de data para formato DD/MM/AAAA.
 * @param {string|null} dateStr
 * @returns {string}
 */
function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        return new Date(dateStr).toLocaleDateString('pt-BR');
    } catch (_) {
        return dateStr;
    }
}

/**
 * Formata uma string de data/hora para DD/MM/AAAA HH:MM.
 * @param {string|null} dateStr
 * @returns {string}
 */
function formatDateTime(dateStr) {
    if (!dateStr) return '—';
    try {
        return new Date(dateStr).toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch (_) {
        return dateStr;
    }
}

/**
 * Retorna data relativa (ex: "há 2 dias" ou "em 3 dias").
 * @param {string|null} dateStr
 * @returns {string}
 */
function formatRelativeDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const now = new Date();
        const date = new Date(dateStr);
        const diffMs = now - date;
        const absDays = Math.floor(Math.abs(diffMs) / (1000 * 60 * 60 * 24));
        const isFuture = diffMs < 0;

        if (absDays === 0) return 'hoje';

        if (isFuture) {
            if (absDays === 1)   return 'amanhã';
            if (absDays < 7)    return `em ${absDays} dias`;
            if (absDays < 30)   return `em ${Math.floor(absDays / 7)} semanas`;
            if (absDays < 365)  return `em ${Math.floor(absDays / 30)} meses`;
            return `em ${Math.floor(absDays / 365)} anos`;
        }

        if (absDays === 1)   return 'ontem';
        if (absDays < 7)    return `há ${absDays} dias`;
        if (absDays < 30)   return `há ${Math.floor(absDays / 7)} semanas`;
        if (absDays < 365)  return `há ${Math.floor(absDays / 30)} meses`;
        return `há ${Math.floor(absDays / 365)} anos`;
    } catch (_) {
        return dateStr;
    }
}

/**
 * Formata um valor numérico como moeda BRL.
 * @param {number|string|null} value
 * @returns {string}
 */
function formatCurrency(value) {
    if (value === null || value === undefined || value === '') return '—';
    const num = parseFloat(value);
    if (isNaN(num)) return '—';
    return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
