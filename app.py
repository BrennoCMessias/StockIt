# --- START OF FILE app.py ---

from flask import Flask, render_template, request, jsonify, url_for
import sqlite3
import os
from datetime import datetime
import logging # Para logs
import pandas as pd # <<--- IMPORT NECESSÁRIO
import traceback # Para debug de erros internos

# Importar funções do módulo helper
try:
    import helper_module # <<--- IMPORT NECESSÁRIO
    logging.info("Módulo helper_module.py importado com sucesso.")
except ImportError as e:
    logging.error(f"ERRO CRÍTICO: Não foi possível importar helper_module.py: {e}. As previsões não funcionarão.")
    # Definir função dummy para evitar erros fatais na execução das rotas
    def obter_previsao_sklearn_dummy(*args, **kwargs):
        return {'previsao': None, 'message': 'Erro: Módulo de previsão (helper_module.py) não encontrado ou contém erros.', 'metodo': 'Erro Interno'}
    # Criar um objeto 'mock' para substituir o módulo
    helper_module = type('obj', (object,), {'obter_previsao_sklearn': obter_previsao_sklearn_dummy})()


app = Flask(__name__)
app.static_folder = 'static'

DATABASE = 'database.db'

# Configuração de Logging
# Adiciona um handler para exibir logs no terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

# Função para conectar ao banco de dados
def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE, timeout=10)
        conn.row_factory = sqlite3.Row
        # --- ADICIONAR ESTA LINHA ---
        conn.execute("PRAGMA foreign_keys = ON;")
        # ---------------------------
        logging.debug("Conexão DB estabelecida com Foreign Keys ATIVADAS.") # Log para confirmar
        return conn
    except sqlite3.Error as e:
        logging.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

# Função para inicializar o banco de dados
def init_db():
    if not os.path.exists(DATABASE):
        logging.info(f"Criando banco de dados em {DATABASE}")
        conn = get_db_connection()
        if conn:
            try:
                with conn:
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS estoque (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT NOT NULL UNIQUE,
                            quantidade INTEGER NOT NULL CHECK(quantidade >= 0),
                            data_cadastro TEXT NOT NULL
                        )
                    ''')
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS consumo (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            item_id INTEGER NOT NULL,
                            quantidade INTEGER NOT NULL CHECK(quantidade > 0),
                            data_consumo TEXT NOT NULL,
                            FOREIGN KEY (item_id) REFERENCES estoque(id) ON DELETE CASCADE
                        )
                    ''')
                logging.info("Tabelas 'estoque' e 'consumo' criadas ou verificadas.")
            except sqlite3.Error as e:
                logging.error(f"Erro ao inicializar tabelas: {e}")
            finally:
                conn.close()
        else:
             logging.critical("Falha na conexão com DB, não foi possível inicializar tabelas.")
    else:
        logging.debug(f"Banco de dados {DATABASE} já existe.")
        # Verificar schema pode ser feito aqui se necessário
        # Por exemplo, adicionando uma coluna se ela não existir


# Filtro Jinja para formatar data/hora
def format_datetime_filter(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        # Tentar formato ISO (com T ou espaço)
        try:
            dt_obj = datetime.fromisoformat(value.replace(' ', 'T'))
        except ValueError:
             # Tentar formato YYYY-MM-DD
            dt_obj = datetime.strptime(value, '%Y-%m-%d')

        # Formatar com hora se não for meia-noite, senão só data
        return dt_obj.strftime("%d/%m/%Y %H:%M") if dt_obj.hour != 0 or dt_obj.minute != 0 else dt_obj.strftime("%d/%m/%Y")
    except (ValueError, TypeError) as e:
        logging.warning(f"Falha ao formatar data '{value}': {e}")
        return "Data Inválida"

app.jinja_env.filters['strftime'] = format_datetime_filter

# --- ROTAS PRINCIPAIS (HTML) ---

@app.route('/')
def principal():
    logging.info("Acessando rota principal /")
    return render_template('principal.html')

@app.route('/estoque')
def estoque_page():
    logging.info("Acessando rota /estoque (página HTML)")
    conn = get_db_connection()
    if not conn: return render_template('error.html', message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        itens = conn.execute('SELECT * FROM estoque ORDER BY nome COLLATE NOCASE').fetchall()
        logging.debug(f"Encontrados {len(itens)} itens para a página de estoque.")
        return render_template('estoque.html', itens=itens)
    except sqlite3.Error as e:
        logging.error(f"Erro DB em /estoque (página): {e}")
        return render_template('error.html', message=f'Erro ao carregar estoque: {e}'), 500
    finally:
        if conn: conn.close()

@app.route('/estatisticas')
def estatisticas_page():
    logging.info("Acessando rota /estatisticas (página HTML)")
    conn = get_db_connection()
    if not conn: return render_template('error.html', message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    dados_template = {}
    try:
        itens_consumo_raw = conn.execute('''
            SELECT e.nome, c.data_consumo, c.quantidade
            FROM consumo c JOIN estoque e ON c.item_id = e.id
            ORDER BY e.nome COLLATE NOCASE, c.data_consumo DESC
        ''').fetchall()
        logging.debug(f"Encontrados {len(itens_consumo_raw)} registros de consumo para estatísticas.")

        for item in itens_consumo_raw:
            nome = item['nome']
            if nome not in dados_template: dados_template[nome] = []
            dados_template[nome].append(dict(item))

        return render_template('estatisticas.html', dados_grafico=dados_template)
    except sqlite3.Error as e:
        logging.error(f"Erro DB em /estatisticas (página): {e}")
        return render_template('error.html', message=f'Erro ao carregar estatísticas: {e}'), 500
    finally:
        if conn: conn.close()

# --- ROTAS DE API (JSON) ---

@app.route('/api/estoque')
def api_get_estoque():
    logging.info("Acessando API /api/estoque")
    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        itens = conn.execute('SELECT id, nome, quantidade FROM estoque ORDER BY nome COLLATE NOCASE').fetchall()
        logging.debug(f"API /api/estoque retornando {len(itens)} itens.")
        return jsonify([dict(row) for row in itens])
    except sqlite3.Error as e:
        logging.error(f"Erro DB em API /api/estoque: {e}")
        return jsonify(message=f'Erro ao buscar dados de estoque: {e}'), 500
    finally:
        if conn: conn.close()

# Função auxiliar para buscar dados de consumo para previsão
def fetch_consumo_data_for_prediction(item_id, conn):
     try:
        df = pd.read_sql_query(
            "SELECT data_consumo, quantidade FROM consumo WHERE item_id = ? ORDER BY data_consumo ASC",
            conn,
            params=(item_id,)
        )
        logging.debug(f"Buscados {len(df)} registros de consumo para item {item_id} para previsão.")
        return df
     except sqlite3.Error as e:
        logging.error(f"Erro DB ao buscar consumo para item {item_id}: {e}")
        return None
     except Exception as pd_err:
        logging.error(f"Erro Pandas ao buscar consumo para item {item_id}: {pd_err}")
        return None

# === ROTA DA API DE PREVISÃO (ESSENCIAL) ===
@app.route('/api/prever/<int:item_id>')
def api_prever_consumo(item_id):
    logging.info(f"Acessando API /api/prever/{item_id}")
    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500

    item_info = None
    df_consumo = None
    try:
        # 1. Buscar informações básicas do item
        item_info = conn.execute('SELECT nome, quantidade FROM estoque WHERE id = ?', (item_id,)).fetchone()
        if not item_info:
            logging.warning(f"API /api/prever: Item com ID {item_id} não encontrado no estoque.")
            return jsonify(message=f'Item com ID {item_id} não encontrado.'), 404

        # 2. Buscar histórico de consumo
        df_consumo = fetch_consumo_data_for_prediction(item_id, conn)
        if df_consumo is None: # Erro já logado na função auxiliar
             return jsonify(message='Erro interno ao buscar histórico de consumo.'), 500

        # 3. Chamar a função de previsão do helper_module
        logging.debug(f"Chamando helper_module.obter_previsao_sklearn para item {item_id} ({item_info['nome']}) com {len(df_consumo)} registros históricos.")
        resultado_previsao = helper_module.obter_previsao_sklearn(df_consumo) # Passa o DataFrame

        # 4. Adicionar info do item ao resultado e logar
        resultado_previsao['item_id'] = item_id
        resultado_previsao['nome_item'] = item_info['nome']
        resultado_previsao['estoque_atual'] = item_info['quantidade']
        logging.info(f"Previsão para item {item_id} ({item_info['nome']}): {resultado_previsao.get('previsao', 'N/A')}, Método: {resultado_previsao.get('metodo', 'N/A')}")

        return jsonify(resultado_previsao)

    except Exception as e:
        logging.error(f"Erro inesperado na API /api/prever/{item_id}: {e}\n{traceback.format_exc()}")
        return jsonify(message=f'Erro inesperado no servidor ao prever item {item_id}. Verifique os logs.'), 500
    finally:
        if conn: conn.close()
# === FIM DA ROTA DA API DE PREVISÃO ===

# --- ROTAS DE AÇÃO (POST) ---

@app.route('/adicionar', methods=['POST'])
def adicionar_item():
    logging.info("Recebida requisição POST em /adicionar")
    nome = request.form.get('nome', '').strip()
    quantidade_str = request.form.get('quantidade')
    data_cadastro = request.form.get('data_cadastro')

    if not nome or not quantidade_str or not data_cadastro:
        logging.warning("Requisição /adicionar com campos faltando.")
        return jsonify(message='Campos obrigatórios faltando (nome, quantidade, data_cadastro)'), 400

    try:
        quantidade = int(quantidade_str)
        if quantidade < 0:
            logging.warning(f"Tentativa de adicionar item '{nome}' com quantidade negativa: {quantidade}")
            return jsonify(message='Quantidade não pode ser negativa.'), 400
        datetime.strptime(data_cadastro, '%Y-%m-%d') # Validar formato data
    except ValueError:
        logging.warning(f"Requisição /adicionar com quantidade ou data inválida. Qtd='{quantidade_str}', Data='{data_cadastro}'")
        return jsonify(message='Quantidade inválida ou formato de data incorreto (esperado YYYY-MM-DD).'), 400

    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        with conn:
            conn.execute('INSERT INTO estoque (nome, quantidade, data_cadastro) VALUES (?, ?, ?)',
                           (nome, quantidade, data_cadastro))
        logging.info(f"Item '{nome}' (Qtd: {quantidade}) adicionado com sucesso.")
        return jsonify(message='Item adicionado com sucesso'), 201
    except sqlite3.IntegrityError:
        logging.warning(f"Tentativa de adicionar item duplicado (UNIQUE constraint): '{nome}'")
        return jsonify(message=f'Erro: Já existe um item com o nome "{nome}".'), 409
    except sqlite3.Error as e:
        logging.error(f"Erro DB ao adicionar item '{nome}': {e}")
        return jsonify(message=f'Erro de banco de dados ao adicionar item: {e}'), 500
    finally:
        if conn: conn.close()

@app.route('/consumir/<int:item_id>', methods=['POST'])
def consumir_item(item_id):
    logging.info(f"Recebida requisição POST em /consumir/{item_id}")
    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT nome, quantidade FROM estoque WHERE id = ?', (item_id,))
            item = cursor.fetchone()

            if item is None:
                logging.warning(f"Tentativa de consumir item inexistente: ID {item_id}")
                return jsonify(message='Item não encontrado.'), 404
            if item['quantidade'] <= 0:
                logging.warning(f"Tentativa de consumir item fora de estoque: ID {item_id} ({item['nome']})")
                return jsonify(message='Item fora de estoque.'), 400

            cursor.execute('UPDATE estoque SET quantidade = quantidade - 1 WHERE id = ?', (item_id,))
            data_consumo_iso = datetime.now().isoformat(timespec='seconds')
            cursor.execute('INSERT INTO consumo (item_id, quantidade, data_consumo) VALUES (?, ?, ?)',
                           (item_id, 1, data_consumo_iso))
            cursor.execute('SELECT quantidade FROM estoque WHERE id = ?', (item_id,))
            nova_quantidade = cursor.fetchone()['quantidade']

        logging.info(f"Item ID {item_id} ({item['nome']}) consumido. Nova quantidade: {nova_quantidade}")
        return jsonify(message='Item consumido com sucesso', nova_quantidade=nova_quantidade), 200
    except sqlite3.Error as e:
        logging.error(f"Erro DB ao consumir item ID {item_id}: {e}")
        return jsonify(message=f'Erro de banco de dados ao consumir item: {e}'), 500
    finally:
        if conn: conn.close()

@app.route('/editar/<int:item_id>', methods=['POST'])
def editar_item(item_id):
    logging.info(f"Recebida requisição POST em /editar/{item_id}")
    nome = request.form.get('nome', '').strip()
    quantidade_str = request.form.get('quantidade')

    if not nome or quantidade_str is None:
        logging.warning(f"Requisição /editar/{item_id} com campos faltando.")
        return jsonify(message='Campos obrigatórios faltando (nome, quantidade)'), 400

    try:
        quantidade = int(quantidade_str)
        if quantidade < 0:
             logging.warning(f"Tentativa de editar item ID {item_id} para quantidade negativa: {quantidade}")
             return jsonify(message='Quantidade não pode ser negativa.'), 400
    except ValueError:
        logging.warning(f"Requisição /editar/{item_id} com quantidade inválida: '{quantidade_str}'")
        return jsonify(message='Quantidade inválida.'), 400

    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM estoque WHERE nome = ? AND id != ?', (nome, item_id))
            if cursor.fetchone():
                 logging.warning(f"Tentativa de editar item ID {item_id} para nome duplicado: '{nome}'")
                 return jsonify(message=f'Erro: Já existe outro item com o nome "{nome}".'), 409

            res = conn.execute('UPDATE estoque SET nome = ?, quantidade = ? WHERE id = ?', (nome, quantidade, item_id))
            if res.rowcount == 0:
                 logging.warning(f"Tentativa de editar item inexistente: ID {item_id}")
                 return jsonify(message='Item não encontrado para editar.'), 404

        logging.info(f"Item ID {item_id} editado para nome='{nome}', quantidade={quantidade}")
        return jsonify(message='Item editado com sucesso')
    except sqlite3.IntegrityError: # Fallback, mas a verificação acima deve pegar
         logging.warning(f"Erro de integridade (UNIQUE) ao editar item ID {item_id} para nome '{nome}'")
         return jsonify(message=f'Erro: Já existe outro item com o nome "{nome}".'), 409
    except sqlite3.Error as e:
        logging.error(f"Erro DB ao editar item ID {item_id}: {e}")
        return jsonify(message=f'Erro de banco de dados ao editar item: {e}'), 500
    finally:
        if conn: conn.close()

@app.route('/excluir/<int:item_id>', methods=['POST'])
def excluir_item(item_id):
    logging.info(f"Recebida requisição POST em /excluir/{item_id}")
    conn = get_db_connection()
    if not conn: return jsonify(message='Erro interno: Falha ao conectar ao banco de dados.'), 500
    try:
        # --- GARANTIR O PRAGMA AQUI TAMBÉM ---
        conn.execute("PRAGMA foreign_keys = ON;")
        logging.debug(f"PRAGMA foreign_keys = ON executado DENTRO de /excluir/{item_id}")
        # ------------------------------------
        with conn: # Usar 'with' para gerenciar transação
            res = conn.execute('DELETE FROM estoque WHERE id = ?', (item_id,))
            if res.rowcount == 0:
                logging.warning(f"Tentativa de excluir item inexistente: ID {item_id}")
                return jsonify(message='Item não encontrado para excluir.'), 404

        logging.info(f"Item ID {item_id} excluído com sucesso (ON DELETE CASCADE deve remover consumo).")
        return jsonify(message='Item excluído com sucesso')
    except sqlite3.Error as e:
        logging.error(f"Erro DB ao excluir o item ID {item_id}: {e}")
        # Verificar se o erro ainda é de FK
        if "FOREIGN KEY constraint failed" in str(e):
             logging.error(">>> ERRO: FALHA DE FOREIGN KEY MESMO COM PRAGMA ATIVO! <<<")
        return jsonify(message=f'Erro de banco de dados ao excluir o item: {e}'), 500
    finally:
        if conn: conn.close()

# --- ERROR HANDLERS ---
@app.errorhandler(404)
def not_found_error(error):
    logging.warning(f"Recurso não encontrado (404): {request.path}")
    if request.path.startswith('/api/'):
        return jsonify(message="Recurso não encontrado."), 404
    return render_template('error.html', message='Página não encontrada (404)'), 404

@app.errorhandler(500)
def internal_error(error):
    # Log completo do erro interno
    logging.error(f"Erro interno no servidor (500) para {request.path}: {error}\n{traceback.format_exc()}")
    if request.path.startswith('/api/'):
        return jsonify(message="Erro interno no servidor. Consulte os logs para detalhes."), 500
    return render_template('error.html', message='Erro interno no servidor (500). O administrador foi notificado.'), 500

@app.errorhandler(400)
def bad_request_error(error):
    desc = error.description if hasattr(error, 'description') else 'Dados inválidos'
    logging.warning(f"Requisição inválida (400) para {request.path}: {desc}")
    # Assumindo API
    return jsonify(message=f"Requisição inválida: {desc}"), 400

# --- INICIALIZAÇÃO ---
if __name__ == '__main__':
    logging.info("=== INICIALIZANDO APLICAÇÃO ===")
    init_db()
    logging.info(f"Iniciando servidor Flask em modo {'DEBUG' if app.debug else 'PRODUÇÃO'}...")
    # Use host='0.0.0.0' para acessível na rede, port pode ser alterado
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=True) # use_reloader=True é padrão com debug=True

# --- END OF FILE app.py ---