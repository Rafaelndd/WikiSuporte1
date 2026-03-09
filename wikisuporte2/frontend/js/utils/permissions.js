/**
 * WikiSuporte 2.0 — Helpers de permissão no frontend
 * Atenção: verificações do lado do cliente são apenas UX.
 * A segurança real é garantida pelo backend.
 */

const Permissions = {
    /** Roles com acesso global (sem filtro por setor) */
    GLOBAL_ROLES: ['ceo', 'admin'],

    /** Verifica se o usuário atual tem acesso de escrita ao módulo */
    canWrite(module) {
        const user = Auth.getCurrentUser();
        if (!user) return false;
        if (this.GLOBAL_ROLES.includes(user.role)) return true;
        // Gestor e analista podem escrever em seus módulos
        const writerRoles = ['gestor', 'analista'];
        return writerRoles.includes(user.role);
    },

    /** Verifica se o usuário atual pode gerenciar configurações */
    canManageSettings() {
        const user = Auth.getCurrentUser();
        if (!user) return false;
        return ['ceo', 'admin', 'gestor'].includes(user.role);
    },

    /** Verifica se o usuário pode gerenciar outros usuários */
    canManageUsers() {
        const user = Auth.getCurrentUser();
        if (!user) return false;
        return ['ceo', 'admin'].includes(user.role);
    },

    /** Verifica se o usuário tem visão global (sem filtro de setor) */
    hasGlobalView() {
        const user = Auth.getCurrentUser();
        if (!user) return false;
        return this.GLOBAL_ROLES.includes(user.role);
    },

    /** Verifica se o usuário tem a role especificada */
    hasRole(role) {
        const user = Auth.getCurrentUser();
        return user?.role === role;
    },

    /** Oculta ou exibe elementos HTML com base em permissão */
    applyVisibility(selector, hasPermission) {
        document.querySelectorAll(selector).forEach(el => {
            el.style.display = hasPermission ? '' : 'none';
        });
    },
};
