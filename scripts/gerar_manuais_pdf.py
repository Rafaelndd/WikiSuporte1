# -*- coding: utf-8 -*-
"""
Gera os manuais em PDF do WikiSuporte (Coordenador e Suporte).
Salva em: Documentação do sistema/Manual_WikiSuporte_Coordenador.pdf
         Documentação do sistema/Manual_WikiSuporte_Suporte.pdf
Execute na raiz do projeto: python scripts/gerar_manuais_pdf.py
"""
import os
import sys

# Raiz do projeto = pasta pai de scripts
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DOC_DIR = os.path.join(ROOT_DIR, "Documentação do sistema")

NOME_SISTEMA = "WikiSuporte"


def _doc_dir():
    """Garante que a pasta de documentação existe."""
    os.makedirs(DOC_DIR, exist_ok=True)
    return DOC_DIR


def _styles():
    """Estilos reportlab reutilizáveis."""
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CapaTitulo",
            parent=styles["Heading1"],
            fontSize=22,
            alignment=TA_CENTER,
            spaceAfter=24,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CapaSubtitulo",
            parent=styles["Normal"],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=36,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Intro",
            parent=styles["Normal"],
            fontSize=11,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Secao",
            parent=styles["Heading1"],
            fontSize=14,
            spaceBefore=18,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Subsec",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Corpo",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Passo",
            parent=styles["Normal"],
            fontSize=10,
            leftIndent=12,
            spaceAfter=4,
        )
    )
    return styles


def _p(styles, name, text):
    from reportlab.platypus import Paragraph
    return Paragraph(text.replace("\n", "<br/>"), styles[name])


def _spacer(h=12):
    from reportlab.platypus import Spacer
    from reportlab.lib.units import mm
    return Spacer(1, h * mm)


def _page_break():
    from reportlab.platypus import PageBreak
    return PageBreak()


# ---------- Conteúdo comum ----------

def _bloco_apresentacao(styles):
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    return [
        _p(styles, "Intro", (
            "O WikiSuporte é a plataforma de suporte técnico da sua equipe. "
            "Por meio dele você acompanha atendimentos, chamados, releases e contribuições "
            "de conhecimento, tudo em um só lugar, de forma organizada e segura."
        )),
        Spacer(1, 8 * mm),
    ]


def _bloco_acesso_login(styles):
    return [
        _p(styles, "Subsec", "Acesso e login"),
        _p(styles, "Corpo", "Para usar o WikiSuporte você precisa abri-lo no navegador e entrar com seu usuário e senha."),
        _p(styles, "Passo", "1. Abra o endereço do WikiSuporte no navegador (o link será informado pela sua empresa)."),
        _p(styles, "Passo", "2. Na tela de login, digite seu usuário no primeiro campo."),
        _p(styles, "Passo", "3. Digite sua senha no segundo campo (a senha não aparece enquanto você digita)."),
        _p(styles, "Passo", "4. Clique no botão <b>Entrar</b>."),
        _p(styles, "Passo", "5. Se os dados estiverem corretos, em instantes você verá a página inicial. Se aparecer mensagem de erro, confira usuário e senha; em caso de dúvida, peça ajuda a quem administra o cadastro (geralmente na área de Configurações)."),
        _spacer(8),
    ]


def _bloco_navegacao(styles):
    return [
        _p(styles, "Subsec", "Como navegar na tela"),
        _p(styles, "Corpo", "Depois do login, a tela é dividida em duas partes principais:"),
        _p(styles, "Passo", "• <b>Barra lateral (lado esquerdo):</b> mostra seu nome, seu perfil (tipo de acesso) e atalhos. Use o botão <b>Sair do Sistema</b> para encerrar sua sessão com segurança."),
        _p(styles, "Passo", "• <b>Menu superior:</b> lista as páginas do sistema (por exemplo: Home, Dashboard de Chamados, Contribuições). Clique no nome da página para abri-la; a área central da tela mostra o conteúdo da página escolhida."),
        _spacer(8),
    ]


def _bloco_home(styles):
    return [
        _p(styles, "Secao", "Página inicial (Home)"),
        _p(styles, "Corpo", "A Home é o seu painel do dia: saudação, previsão do tempo (se disponível), alertas e seus indicadores."),
        _p(styles, "Subsec", "O que aparece na Home"),
        _p(styles, "Passo", "• Saudação (bom dia / boa tarde / boa noite) e seu nome."),
        _p(styles, "Passo", "• Clima atual (informativo)."),
        _p(styles, "Passo", "• Alertas do dia: por exemplo plantão, validações de release pendentes e avisos de representante."),
        _p(styles, "Passo", "• Seus indicadores: nível, XP, posição no ranking e missões."),
        _p(styles, "Passo", "• Central de notificações: lista de avisos pendentes e histórico dos que você já leu."),
        _p(styles, "Subsec", "Passo a passo: como usar os alertas"),
        _p(styles, "Passo", "1. Leia os alertas na seção <b>Central de Notificações</b>."),
        _p(styles, "Passo", "2. Para marcar um aviso como lido, abra o aviso e clique em <b>Marcar como lida</b>."),
        _p(styles, "Passo", "3. Na aba <b>Histórico (Lidas)</b> você pode ver os avisos já lidos e, se quiser, restaurá-los para a lista de pendentes."),
        _spacer(8),
    ]


def _bloco_dashboard_atendimentos(styles):
    return [
        _p(styles, "Secao", "Dashboard de Atendimentos"),
        _p(styles, "Corpo", "Esta tela mostra métricas dos atendimentos por ligação (GoTo) e por chat (Multi360), para acompanhar o desempenho da equipe no período escolhido."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Dashboard Atendimentos</b> no topo."),
        _p(styles, "Passo", "2. Ajuste os <b>Filtros</b>: período (data inicial e final), analista (se quiser ver só um) e cliente (opcional)."),
        _p(styles, "Passo", "3. Use as <b>abas</b> para alternar entre visões: atendimentos GoTo, Multi360 ou visões combinadas."),
        _p(styles, "Passo", "4. Observe os gráficos e tabelas para entender volume, tempo médio e desempenho por analista."),
        _p(styles, "Passo", "5. Use os indicadores para identificar quem mais atendeu e onde há oportunidades de melhoria."),
        _spacer(8),
    ]


def _bloco_importacao(styles):
    return [
        _p(styles, "Secao", "Importação de Dados"),
        _p(styles, "Corpo", "Aqui você envia para o sistema os dados de atendimentos (ligações ou chats), seja por arquivo (planilha) ou pela conexão com o sistema de ligações (GoTo), para que os dashboards e relatórios fiquem atualizados."),
        _p(styles, "Subsec", "Passo a passo (upload de arquivo)"),
        _p(styles, "Passo", "1. Abra o menu <b>Importação de Dados</b>."),
        _p(styles, "Passo", "2. Escolha a aba correspondente (por exemplo, arquivo CSV ou planilha do GoTo/Multi360)."),
        _p(styles, "Passo", "3. Clique em <b>Escolher arquivo</b> e selecione o arquivo no seu computador."),
        _p(styles, "Passo", "4. Aguarde o processamento. Se o sistema pedir cadastro de cliente para algum número ainda sem vínculo, preencha a razão social (e CNPJ se tiver) para melhorar os relatórios depois."),
        _p(styles, "Passo", "5. Clique em <b>Salvar</b> ou no botão indicado para gravar os dados no sistema."),
        _p(styles, "Corpo", "Se a sua empresa usar a conexão direta com o GoTo, a importação pode ser feita por essa opção na mesma tela; siga as orientações exibidas no próprio sistema."),
        _spacer(8),
    ]


def _bloco_dashboard_chamados(styles):
    return [
        _p(styles, "Secao", "Dashboard de Chamados"),
        _p(styles, "Corpo", "Nesta tela você acompanha chamados de suporte: quantidade, status, tempos de espera, versões e desempenho. Os filtros permitem ver um período, um analista ou todos, e focar em abertos ou encerrados."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Dashboard Chamados</b>."),
        _p(styles, "Passo", "2. Defina o <b>período</b>, o <b>analista</b> (ou Todos) e o <b>status</b> (abertos, encerrados, etc.), conforme as opções disponíveis."),
        _p(styles, "Passo", "3. Navegue pelas <b>abas</b>: visão geral, tempos de espera, detalhes por versão, performance, homologação."),
        _p(styles, "Passo", "4. Use os gráficos e tabelas para analisar volume, prazos e andamento das versões."),
        _p(styles, "Passo", "5. Quando houver classificação por categoria (Erro, Melhoria, Adequação Fiscal), você pode filtrar por categoria na aba de versões."),
        _spacer(8),
    ]


def _bloco_configuracoes(styles):
    return [
        _p(styles, "Secao", "Configurações"),
        _p(styles, "Corpo", "As Configurações reúnem ferramentas de administração: status dos bots de atualização, ramais e analistas, usuários, clientes e telefones, notificações e auditoria. Use com moderação e conforme orientação da TI."),
        _p(styles, "Subsec", "Abas principais"),
        _p(styles, "Passo", "• <b>Bots:</b> ver o status dos processos que atualizam dados do helpdesk; solicitar uma nova varredura quando necessário (respeitando os limites de segurança)."),
        _p(styles, "Passo", "• <b>Ramais e Analistas:</b> consultar e ajustar ramais e vínculos de analistas."),
        _p(styles, "Passo", "• <b>Usuários:</b> criar novos usuários e alterar perfil ou senha (exceto do usuário desenvolvedor, que só pode ser alterado por ele mesmo)."),
        _p(styles, "Passo", "• <b>Clientes e telefones:</b> cadastrar clientes e números de telefone para que os dados de atendimento sejam identificados corretamente nos relatórios."),
        _p(styles, "Passo", "• <b>Notificações e Auditoria:</b> configurar avisos e consultar o registro de ações importantes no sistema."),
        _p(styles, "Corpo", "Em caso de dúvida sobre o que fazer em cada aba, consulte o gestor ou a equipe de TI."),
        _spacer(8),
    ]


def _bloco_dashboard_tickets(styles):
    return [
        _p(styles, "Secao", "Dashboard Tickets EPSY"),
        _p(styles, "Corpo", "Esta tela exibe indicadores e métricas dos tickets da operação. Use os filtros (período, analista, etc.) para analisar o desempenho e o volume de atendimentos."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Dashboard Tickets EPSY</b>."),
        _p(styles, "Passo", "2. Ajuste os filtros conforme necessário."),
        _p(styles, "Passo", "3. Analise os gráficos e números exibidos para acompanhar o dia a dia da equipe."),
        _spacer(8),
    ]


def _bloco_contribuicoes_coord(styles):
    return [
        _p(styles, "Secao", "Contribuições Suporte"),
        _p(styles, "Corpo", "Aqui a equipe publica dicas e soluções que passam a fazer parte da base de conhecimento. Como coordenador, você pode criar dicas, usar ferramentas de IA (quando disponíveis), aprovar ou reprovar as contribuições dos analistas e votar ou marcar itens como obsoletos."),
        _p(styles, "Subsec", "Criar uma dica"),
        _p(styles, "Passo", "1. Abra o menu <b>Contribuições Suporte</b>."),
        _p(styles, "Passo", "2. Preencha título, categoria (e subcategoria se houver), conteúdo da dica e anexe arquivo se precisar."),
        _p(styles, "Passo", "3. Se a IA estiver disponível para seu perfil, você pode usá-la para enriquecer o texto."),
        _p(styles, "Passo", "4. Clique em salvar ou publicar; como coordenador, a dica pode ir direto como aprovada."),
        _p(styles, "Subsec", "Aprovar ou reprovar contribuições dos analistas"),
        _p(styles, "Passo", "1. Na mesma tela, localize a lista de contribuições pendentes de aprovação."),
        _p(styles, "Passo", "2. Abra a contribuição e leia o conteúdo."),
        _p(styles, "Passo", "3. Clique em <b>Aprovar</b> para publicar na base ou em <b>Reprovar</b>; se reprovar, informe um motivo claro para o analista corrigir."),
        _p(styles, "Subsec", "Votar e marcar obsoleto"),
        _p(styles, "Passo", "• Use o botão de curtir (votar) nas dicas que achar úteis."),
        _p(styles, "Passo", "• Se uma dica não for mais válida, use a opção de marcar como obsoleta (quando disponível para seu perfil)."),
        _spacer(8),
    ]


def _bloco_contribuicoes_suporte(styles):
    return [
        _p(styles, "Secao", "Contribuições Suporte"),
        _p(styles, "Corpo", "Aqui você pode publicar dicas e soluções para a equipe. Suas contribuições ficam <b>pendentes</b> até que um coordenador aprove. Você também pode votar nas dicas dos colegas."),
        _p(styles, "Subsec", "Criar uma dica"),
        _p(styles, "Passo", "1. Abra o menu <b>Contribuições Suporte</b>."),
        _p(styles, "Passo", "2. Preencha o <b>título</b>, a <b>categoria</b> (e subcategoria se existir) e o <b>conteúdo</b> da dica."),
        _p(styles, "Passo", "3. Se quiser, anexe um arquivo (PDF, imagem, etc.) que ajude a explicar o passo a passo."),
        _p(styles, "Passo", "4. Clique em salvar ou enviar. A dica ficará como <b>pendente</b> até um coordenador aprovar."),
        _p(styles, "Subsec", "Votar em dicas dos colegas"),
        _p(styles, "Passo", "1. Na lista de dicas aprovadas, use o botão de curtir (ou equivalente) nas dicas que você achar úteis."),
        _p(styles, "Passo", "2. Sua votação ajuda a destacar as melhores contribuições da equipe."),
        _spacer(8),
    ]


def _bloco_feedback(styles):
    return [
        _p(styles, "Secao", "Canal de Feedback"),
        _p(styles, "Corpo", "Use esta página para enviar sugestões, relatar problemas, dar ideias de melhoria ou enviar elogios. As mensagens são encaminhadas ao responsável técnico."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Feedback</b>."),
        _p(styles, "Passo", "2. Preencha o <b>Assunto</b> e a <b>Descrição</b> (obrigatórios)."),
        _p(styles, "Passo", "3. Escolha o <b>tipo</b> (sugestão, bug, melhoria, elogio, etc.)."),
        _p(styles, "Passo", "4. Se quiser receber resposta por e-mail, informe seu e-mail no campo indicado."),
        _p(styles, "Passo", "5. Clique em enviar e aguarde a confirmação na tela."),
        _spacer(8),
    ]


def _bloco_registro_coord(styles):
    return [
        _p(styles, "Secao", "Registro de Atendimentos"),
        _p(styles, "Corpo", "Aqui você consulta os registros de atendimentos (ligações e chats). Como coordenador, pode filtrar por analista e exportar o resultado em PDF."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Registro de Atendimentos</b>."),
        _p(styles, "Passo", "2. Defina período e, se disponível, escolha o <b>Analista</b> (ou Todos)."),
        _p(styles, "Passo", "3. Visualize a tabela e use a opção de <b>Exportar PDF</b> quando precisar guardar ou imprimir o relatório."),
        _p(styles, "Corpo", "Os analistas veem a mesma tela, mas normalmente apenas seus próprios atendimentos, sem o filtro por outros analistas."),
        _spacer(8),
    ]


def _bloco_registro_suporte(styles):
    return [
        _p(styles, "Secao", "Registro de Atendimentos"),
        _p(styles, "Corpo", "Aqui você consulta os registros dos seus atendimentos (ligações e chats) no período escolhido."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Registro de Atendimentos</b>."),
        _p(styles, "Passo", "2. Defina o período dos dados que deseja ver."),
        _p(styles, "Passo", "3. Visualize a tabela. Se houver opção de exportar em PDF, use-a para guardar ou imprimir seu relatório."),
        _spacer(8),
    ]


def _bloco_releases_coord(styles):
    return [
        _p(styles, "Secao", "Releases Tecnuv (manual)"),
        _p(styles, "Corpo", "Nesta tela você envia o arquivo da release, informa a versão, cria os ciclos de teste e aprova ou reprova as validações na auditoria."),
        _p(styles, "Subsec", "Enviar release e criar ciclos"),
        _p(styles, "Passo", "1. Abra o menu <b>Releases Tecnuv (manual)</b>."),
        _p(styles, "Passo", "2. Envie o arquivo da release e informe a <b>versão</b>."),
        _p(styles, "Passo", "3. O sistema cria os ciclos de teste conforme configurado."),
        _p(styles, "Subsec", "Aprovar ou reprovar na auditoria"),
        _p(styles, "Passo", "1. Na área de auditoria, localize as validações pendentes."),
        _p(styles, "Passo", "2. Para cada item, altere o status para <b>Aprovado</b> ou <b>Reprovado</b>."),
        _p(styles, "Passo", "3. Se reprovar, preencha o <b>motivo</b> para que o analista saiba o que ajustar."),
        _p(styles, "Passo", "4. Salve. Acompanhe as validações até concluir o ciclo."),
        _spacer(8),
    ]


def _bloco_releases_suporte(styles):
    return [
        _p(styles, "Secao", "Releases Tecnuv (manual)"),
        _p(styles, "Corpo", "Aqui você vê as validações de release que envolvem seus chamados. Quando for sua responsabilidade validar, você registra aprovação ou reprovação. O envio do arquivo da release e a gestão dos ciclos ficam a cargo da coordenação."),
        _p(styles, "Subsec", "Passo a passo"),
        _p(styles, "Passo", "1. Abra o menu <b>Releases Tecnuv (manual)</b>."),
        _p(styles, "Passo", "2. Verifique a lista de <b>validações pendentes</b> (quando houver avisos na Home, eles se referem a isso)."),
        _p(styles, "Passo", "3. Para o seu chamado, abra o item e registre <b>Aprovado</b> ou <b>Reprovado</b>; se reprovar, informe o motivo."),
        _p(styles, "Passo", "4. Salve. A coordenação acompanha o andamento geral dos ciclos."),
        _spacer(8),
    ]


def _bloco_menus_apenas_coordenacao(styles):
    return [
        _p(styles, "Secao", "Menus que só a coordenação vê"),
        _p(styles, "Corpo", "Alguns itens do menu aparecem apenas para coordenadores e equipe de desenvolvimento. Isso é normal: Importação de Dados, Configurações e Dashboard de Atendimentos são usados pela coordenação para atualizar dados, administrar usuários e clientes e analisar métricas da equipe. Se você achar que deveria ter acesso a alguma área, converse com seu gestor ou com a equipe de TI."),
        _spacer(8),
    ]


def _bloco_encerramento_coord(styles):
    return [
        _p(styles, "Secao", "Onde obter mais ajuda"),
        _p(styles, "Corpo", "Em caso de dúvida sobre o uso do WikiSuporte, consulte seu gestor ou a equipe de TI. A documentação técnica (para desenvolvedores) pode trazer detalhes adicionais quando necessário."),
        _spacer(8),
    ]


def _bloco_encerramento_suporte(styles):
    return [
        _p(styles, "Secao", "Onde obter mais ajuda"),
        _p(styles, "Corpo", "Se tiver dúvidas ou precisar de acesso a alguma função que não aparece no seu menu, fale com seu coordenador ou gestor. Eles poderão orientar ou solicitar o acesso adequado à equipe de TI."),
        _spacer(8),
    ]


def build_story_coordenador(styles):
    """Monta a lista de flowables do manual do coordenador."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.units import mm

    story = []
    # Capa
    story.append(_spacer(40))
    story.append(_p(styles, "CapaTitulo", NOME_SISTEMA + " — Manual do usuário"))
    story.append(_p(styles, "CapaSubtitulo", "Versão para Coordenador"))
    story.append(_spacer(20))
    story.extend(_bloco_apresentacao(styles))
    story.append(_page_break())

    # Comum
    story.extend(_bloco_acesso_login(styles))
    story.extend(_bloco_navegacao(styles))
    story.extend(_bloco_home(styles))

    # Específicos coordenador
    story.extend(_bloco_dashboard_atendimentos(styles))
    story.extend(_bloco_importacao(styles))
    story.extend(_bloco_dashboard_chamados(styles))
    story.extend(_bloco_configuracoes(styles))
    story.extend(_bloco_dashboard_tickets(styles))
    story.extend(_bloco_contribuicoes_coord(styles))
    story.extend(_bloco_feedback(styles))
    story.extend(_bloco_registro_coord(styles))
    story.extend(_bloco_releases_coord(styles))
    story.extend(_bloco_encerramento_coord(styles))
    return story


def build_story_suporte(styles):
    """Monta a lista de flowables do manual do suporte (analista)."""
    from reportlab.platypus import PageBreak

    story = []
    # Capa
    story.append(_spacer(40))
    story.append(_p(styles, "CapaTitulo", NOME_SISTEMA + " — Manual do usuário"))
    story.append(_p(styles, "CapaSubtitulo", "Versão para Suporte (Analista)"))
    story.append(_spacer(20))
    story.extend(_bloco_apresentacao(styles))
    story.append(_page_break())

    # Comum
    story.extend(_bloco_acesso_login(styles))
    story.extend(_bloco_navegacao(styles))
    story.extend(_bloco_home(styles))
    story.extend(_bloco_menus_apenas_coordenacao(styles))

    # Específicos suporte
    story.extend(_bloco_dashboard_chamados(styles))
    story.extend(_bloco_dashboard_tickets(styles))
    story.extend(_bloco_contribuicoes_suporte(styles))
    story.extend(_bloco_feedback(styles))
    story.extend(_bloco_registro_suporte(styles))
    story.extend(_bloco_releases_suporte(styles))
    story.extend(_bloco_encerramento_suporte(styles))
    return story


def gerar_pdf_coordenador():
    """Gera Manual_WikiSuporte_Coordenador.pdf em Documentação do sistema/."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate

    _doc_dir()
    path = os.path.join(DOC_DIR, "Manual_WikiSuporte_Coordenador.pdf")
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=40,
    )
    styles = _styles()
    story = build_story_coordenador(styles)
    doc.build(story)
    return path


def gerar_pdf_suporte():
    """Gera Manual_WikiSuporte_Suporte.pdf em Documentação do sistema/."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate

    _doc_dir()
    path = os.path.join(DOC_DIR, "Manual_WikiSuporte_Suporte.pdf")
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=40,
    )
    styles = _styles()
    story = build_story_suporte(styles)
    doc.build(story)
    return path


def main():
    sys.path.insert(0, ROOT_DIR)
    print("Gerando manuais PDF do WikiSuporte...")
    path_coord = gerar_pdf_coordenador()
    print("  Gerado:", path_coord)
    path_sup = gerar_pdf_suporte()
    print("  Gerado:", path_sup)
    print("Concluído. Os arquivos estão em:", DOC_DIR)


if __name__ == "__main__":
    main()
