from nicegui import app, ui
import psutil
import os
import socket
import time
import subprocess
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import speedtest  # Para testes de rede (instale via pip se necessário, mas assumindo ambiente com suporte)

# Carrega variáveis de ambiente (DB_HOST, DB_NAME, DB_USER, DB_PASS)
load_dotenv()

# ==========================================
# 1. CONEXÃO COM O BANCO (PostgreSQL)
# ==========================================
def get_db_engine():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5455")
    db = os.getenv("DB_NAME", "central_chamados")
    user = os.getenv("DB_USER", "postgres")
    pwd = os.getenv("DB_PASS", "")
    return create_engine(f"postgresql://{user}:{pwd}@{host}:{port}/{db}")

engine = get_db_engine()

# ==========================================
# 2. SISTEMA DE AUTENTICAÇÃO SEGURO
# ==========================================
def validar_login(usuario, senha_digitada):
    """Consulta o PostgreSQL delegando a validação do hash ao pgcrypto."""
    try:
        with engine.connect() as conn:
            # Verifica se o usuário é desenvolvedor e se a senha bate com o hash
            query = text("""
                SELECT id, nome FROM usuarios 
                WHERE nome = :u 
                AND perfil = 'desenvolvedor' 
                AND password_hash = crypt(:p, password_hash)
            """)
            resultado = conn.execute(query, {"u": usuario, "p": senha_digitada}).fetchone()
            
            if resultado:
                app.storage.user.update({'autenticado': True, 'nome': resultado.nome})
                ui.navigate.to('/')
            else:
                ui.notify('Acesso Negado. Credenciais inválidas ou sem permissão.', type='negative')
    except Exception as e:
        ui.notify(f'Erro de conexão com o banco: {e}', type='negative')

def logout():
    app.storage.user.clear()
    ui.navigate.to('/login')

# ==========================================
# 3. TELA DE LOGIN (/login)
# ==========================================
@ui.page('/login')
def login_page():
    # Se já estiver logado, manda pro painel
    if app.storage.user.get('autenticado', False):
        ui.navigate.to('/')
        return

    with ui.card().classes('absolute-center w-96 p-8 shadow-2xl rounded-xl'):
        ui.label('🛡️ Sentinela').classes('text-3xl font-bold mb-2 text-center w-full text-blue-900')
        ui.label('Acesso Restrito ao Desenvolvedor').classes('text-sm mb-6 text-center w-full text-gray-500')
        
        input_user = ui.input('Usuário Admin').classes('w-full mb-4')
        input_pass = ui.input('Senha', password=True, password_toggle_button=True).classes('w-full mb-6')
        
        ui.button('Autenticar e Inspecionar', on_click=lambda: validar_login(input_user.value, input_pass.value)).classes('w-full')

# ==========================================
# 4. O PAINEL DE DIAGNÓSTICO PROFUNDO (/)
# ==========================================
@ui.page('/')
def dashboard():
    # Bloqueio de Rota (Guard)
    if not app.storage.user.get('autenticado', False):
        ui.navigate.to('/login')
        return

    # Cabeçalho Superior
    with ui.header().classes('justify-between items-center p-4 bg-slate-900'):
        ui.label('📡 Telemetria e Diagnóstico de Gargalos').classes('text-xl font-bold text-white')
        with ui.row().classes('items-center'):
            ui.label(f"Logado como: {app.storage.user.get('nome')}").classes('text-gray-300 mr-4')
            ui.button('Sair', on_click=logout, color='red-8').props('size=sm')

    # Grid de Layout (agora com mais colunas para acomodar novas seções)
    with ui.grid(columns=3).classes('w-full gap-6 p-6'):
        
        # --- BLOCO A: ANÁLISE PREDITIVA DO SERVIDOR ---
        with ui.card().classes('col-span-1 shadow-md'):
            ui.label('💻 Capacidade do Servidor e Alertas').classes('text-lg font-bold mb-4')
            
            cpu_label = ui.label('Carga de Processamento (Load Average): Calculando...')
            cpu_prog = ui.linear_progress(value=0).props('color="blue"')
            
            ram_label = ui.label('Uso de RAM (Risco de Vazamento): Calculando...')
            ram_prog = ui.linear_progress(value=0).props('color="green"')
            
            disco_label = ui.label('Esgotamento de Armazenamento: Calculando...')
            disco_prog = ui.linear_progress(value=0).props('color="orange"')

            # Nova: Temperatura do CPU (se disponível via psutil)
            temp_label = ui.label('Temperatura do CPU: Calculando...')

        # --- BLOCO B: SAÚDE DO POSTGRESQL E USUÁRIOS ---
        with ui.card().classes('col-span-1 shadow-md'):
            ui.label('🗄️ Saúde do Banco de Dados').classes('text-lg font-bold mb-4')
            
            db_conn_label = ui.label('Processos no Banco: Calculando...')
            db_locks_label = ui.label('Transações Travadas: Calculando...')
            db_size_label = ui.label('Peso de Tabelas Críticas: Calculando...')
            
            usuarios_ativos_label = ui.label('Contas de Usuário Ativas no Banco: Lendo...').classes('font-semibold mt-4')
            
            # Painel expansível para usuários
            with ui.expansion('Ver Lista Detalhada', icon='group').classes('w-full bg-slate-50 rounded-md border mt-2') as expansao_usuarios:
                tabela_usuarios_ativos = ui.table(
                    columns=[
                        {'name': 'nome', 'label': 'Usuário', 'field': 'nome', 'align': 'left'},
                        {'name': 'perfil', 'label': 'Perfil de Acesso', 'field': 'perfil', 'align': 'left'}
                    ],
                    rows=[],
                    row_key='nome'
                ).classes('w-full').props('dense flat')

            # Nova: Saúde do Vacuum e Índices
            vacuum_label = ui.label('Status de Vacuum/Analyze: Calculando...')

        # --- BLOCO C: QUALIDADE DA REDE E SEGURANÇA ---
        with ui.card().classes('col-span-1 shadow-md'):
            ui.label('🌐 Qualidade da Rede e Segurança').classes('text-lg font-bold mb-4')
            
            rede_io_label = ui.label('Tráfego de Rede: Calculando...')
            rede_latencia_label = ui.label('Latência de Rede: Calculando...')
            rede_velocidade_label = ui.label('Velocidade de Internet: Calculando...')
            
            conexoes_abertas_label = ui.label('Conexões Abertas (Potenciais Vazamentos): Calculando...')
            
            # Painel expansível para conexões suspeitas
            with ui.expansion('Ver Conexões Detalhadas', icon='security').classes('w-full bg-slate-50 rounded-md border mt-2') as expansao_conexoes:
                tabela_conexoes = ui.table(
                    columns=[
                        {'name': 'pid', 'label': 'PID', 'field': 'pid'},
                        {'name': 'laddr', 'label': 'Endereço Local', 'field': 'laddr'},
                        {'name': 'raddr', 'label': 'Endereço Remoto', 'field': 'raddr'},
                        {'name': 'status', 'label': 'Status', 'field': 'status'}
                    ],
                    rows=[],
                    row_key='pid'
                ).classes('w-full').props('dense flat')

        # --- BLOCO D: QUERIES LENTAS (GARGALOS) ---
        with ui.card().classes('col-span-2 shadow-md'):
            ui.label('🚨 Gargalos Atuais (Queries Lentas em Tempo Real)').classes('text-lg font-bold text-red-700')
            tabela_queries = ui.table(
                columns=[
                    {'name': 'pid', 'label': 'PID', 'field': 'pid'},
                    {'name': 'duracao', 'label': 'Duração', 'field': 'duracao'},
                    {'name': 'query', 'label': 'Comando SQL', 'field': 'query', 'align': 'left'},
                ],
                rows=[],
                row_key='pid'
            ).classes('w-full')

        # --- BLOCO E: LOGS DO SISTEMA E ALERTAS PREDITIVOS ---
        with ui.card().classes('col-span-1 shadow-md'):
            ui.label('📜 Logs e Antecipação de Problemas').classes('text-lg font-bold mb-4')
            
            logs_erros_label = ui.label('Erros Recentes nos Logs: Calculando...')
            predicao_disco_label = ui.label('Previsão de Esgotamento de Disco: Calculando...')
            predicao_ram_label = ui.label('Previsão de Sobrecarga de RAM: Calculando...')
            
            # Painel expansível para logs
            with ui.expansion('Ver Logs Detalhados', icon='error').classes('w-full bg-slate-50 rounded-md border mt-2') as expansao_logs:
                logs_text = ui.label('Logs: Carregando...')

    # ==========================================
    # 5. O MOTOR DE ATUALIZAÇÃO ASSÍNCRONA
    # ==========================================
    def atualizar_dados():
        # A. Métricas do Host
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage('/')
        temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
        cpu_temp = temps.get('coretemp', [{}])[0].current if temps else 'Não disponível'
        
        # Lógica preditiva para RAM e Disco
        texto_ram = f"Memória RAM: {ram.percent}% "
        if ram.percent > 85:
            texto_ram += " ⚠️ ALERTA: Risco de paginação (Swap) e travamento!"
            ram_prog.props('color="red"')
        else:
            ram_prog.props('color="green"')

        # Previsão simples: assumindo uso linear, prever tempo para 100%
        # (Isso é uma estimativa básica; ajuste com dados históricos para precisão)
        uso_disco_por_minuto = 0.01  # Exemplo: ajuste com medições reais
        tempo_para_lotar_disco = (100 - disco.percent) / uso_disco_por_minuto if uso_disco_por_minuto > 0 else 'Indefinido'
        predicao_disco_label.set_text(f"Previsão de Esgotamento: ~{tempo_para_lotar_disco:.1f} minutos")

        uso_ram_por_minuto = 0.05  # Exemplo
        tempo_para_lotar_ram = (100 - ram.percent) / uso_ram_por_minuto if uso_ram_por_minuto > 0 else 'Indefinido'
        predicao_ram_label.set_text(f"Previsão de Sobrecarga: ~{tempo_para_lotar_ram:.1f} minutos")

        cpu_label.set_text(f"Carga de Processamento: {cpu}%")
        cpu_prog.set_value(cpu / 100)
        ram_label.set_text(texto_ram)
        ram_prog.set_value(ram.percent / 100)
        disco_label.set_text(f"Armazenamento Raiz: {disco.percent}% ({disco.free / (1024**3):.1f} GB Livres)")
        disco_prog.set_value(disco.percent / 100)
        temp_label.set_text(f"Temperatura do CPU: {cpu_temp}°C" if isinstance(cpu_temp, float) else f"Temperatura do CPU: {cpu_temp}")

        # B. Métricas do PostgreSQL
        try:
            with engine.connect() as conn:
                # Processos gerais e transações travadas
                stats = conn.execute(text("""
                    SELECT 
                        count(*) FILTER (WHERE state = 'active') as ativas,
                        count(*) FILTER (WHERE state = 'idle') as ociosas,
                        (SELECT count(*) FROM pg_locks WHERE NOT granted) as travadas
                    FROM pg_stat_activity 
                    WHERE datname = current_database();
                """)).fetchone()
                
                db_conn_label.set_text(f"Processos DB: {stats.ativas} Ativos | {stats.ociosas} Ociosos (Conectados sem uso)")
                
                texto_lock = f"Transações Travadas (Locks): {stats.travadas}"
                if stats.travadas > 0:
                    db_locks_label.set_text(f"⚠️ {texto_lock} -> O banco está bloqueando operações!")
                    db_locks_label.classes(add='text-red-600', remove='text-green-600')
                else:
                    db_locks_label.set_text(f"✅ {texto_lock}")
                    db_locks_label.classes(add='text-green-600', remove='text-red-600')

                # Tamanho de tabelas críticas
                try:
                    tamanho_base = conn.execute(text("SELECT pg_size_pretty(pg_total_relation_size('base_conhecimento'));")).scalar()
                    db_size_label.set_text(f"Peso da Tabela 'base_conhecimento' + Índices: {tamanho_base}")
                except:
                    db_size_label.set_text("Peso de Tabelas Críticas: Tabela não encontrada ou sem acesso.")

                # Usuários ativos
                query_users = text("SELECT nome, perfil FROM usuarios WHERE ativo = true ORDER BY nome ASC;")
                lista_usuarios = conn.execute(query_users).fetchall()
                qtd_ativos = len(lista_usuarios)
                usuarios_ativos_label.set_text(f"Contas de Usuário Ativas no Banco: {qtd_ativos}")
                
                expansao_usuarios.text = f'Ocultar/Mostrar os {qtd_ativos} Usuários'
                expansao_usuarios.update()
                
                tabela_usuarios_ativos.rows = [
                    {'nome': u.nome, 'perfil': u.perfil} 
                    for u in lista_usuarios
                ]
                tabela_usuarios_ativos.update()

                # Saúde do Vacuum (último vacuum e analyze)
                vacuum_stats = conn.execute(text("""
                    SELECT relname, last_vacuum, last_analyze 
                    FROM pg_stat_user_tables 
                    ORDER BY last_vacuum DESC LIMIT 1;
                """)).fetchone()
                if vacuum_stats:
                    vacuum_label.set_text(f"Último Vacuum em {vacuum_stats.relname}: {vacuum_stats.last_vacuum or 'Nunca'} (Analyze: {vacuum_stats.last_analyze or 'Nunca'})")
                else:
                    vacuum_label.set_text("Status de Vacuum: Não disponível")

                # C. Captura de Queries Lentas
                q_lentas = conn.execute(text("""
                    SELECT pid, COALESCE(EXTRACT(EPOCH FROM (now() - query_start))::int, 0) AS duracao, query 
                    FROM pg_stat_activity 
                    WHERE state = 'active' AND now() - query_start > interval '1 seconds'
                    ORDER BY duracao DESC LIMIT 5;
                """)).fetchall()
                
                tabela_queries.rows = [
                    {'pid': q.pid, 'duracao': f"{q.duracao}s", 'query': q.query[:80] + '...' if q.query else ''} 
                    for q in q_lentas
                ]
                tabela_queries.update()

        except Exception as e:
            db_conn_label.set_text(f"Erro de telemetria DB: {e}")

        # D. Métricas de Rede
        net_io = psutil.net_io_counters()
        rede_io_label.set_text(f"Tráfego: Enviados {net_io.bytes_sent / (1024**2):.2f} MB | Recebidos {net_io.bytes_recv / (1024**2):.2f} MB")

        # Latência simples (ping para google.com)
        try:
            latencia = subprocess.check_output(['ping', '-c', '1', 'google.com']).decode()
            latencia_ms = latencia.split('time=')[1].split(' ms')[0] if 'time=' in latencia else 'Erro'
            rede_latencia_label.set_text(f"Latência (Ping Google): {latencia_ms} ms")
        except:
            rede_latencia_label.set_text("Latência: Não disponível")

        # Velocidade de Internet (usando speedtest-cli)
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            download = st.download() / (1024**2)
            upload = st.upload() / (1024**2)
            rede_velocidade_label.set_text(f"Velocidade: Download {download:.2f} Mbps | Upload {upload:.2f} Mbps")
        except:
            rede_velocidade_label.set_text("Velocidade: Não disponível (instale speedtest-cli)")

        # Conexões abertas (potenciais vazamentos)
        conexoes = psutil.net_connections()
        conexoes_suspeitas = [c for c in conexoes if c.status == 'ESTABLISHED' and c.raddr]
        conexoes_abertas_label.set_text(f"Conexões Abertas: {len(conexoes)} (Suspeitas: {len(conexoes_suspeitas)})")
        
        expansao_conexoes.text = f'Ocultar/Mostrar {len(conexoes_suspeitas)} Conexões Suspeitas'
        expansao_conexoes.update()
        
        tabela_conexoes.rows = [
            {'pid': c.pid, 'laddr': f"{c.laddr.ip}:{c.laddr.port}", 'raddr': f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else '', 'status': c.status}
            for c in conexoes_suspeitas[:10]  # Limita a 10 para não sobrecarregar
        ]
        tabela_conexoes.update()

        # E. Logs do Sistema (exemplo: últimos erros do syslog)
        try:
            logs = subprocess.check_output(['tail', '-n', '10', '/var/log/syslog']).decode()
            erros = [line for line in logs.split('\n') if 'error' in line.lower() or 'critical' in line.lower()]
            logs_erros_label.set_text(f"Erros Recentes: {len(erros)} encontrados")
            logs_text.set_text('\n'.join(erros) if erros else 'Nenhum erro recente.')
        except:
            logs_erros_label.set_text("Logs: Não disponível (verifique permissões)")

    # Aciona a leitura a cada 5 segundos (aumentado para não sobrecarregar, ajuste conforme necessário)
    ui.timer(5.0, atualizar_dados)

# Inicia o servidor com suporte a sessões (obrigatório para o login funcionar)
ui.run(port=8080, storage_secret='sua_chave_secreta_super_segura_aqui', dark=True)