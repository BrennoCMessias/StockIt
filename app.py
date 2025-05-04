# --- START OF FILE app.py ---

from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
# Serve static files from the 'static' directory
app.static_folder = 'static' 

DATABASE = 'database.db'

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome
    return conn

# Função para inicializar o banco de dados, se ele não existir
def init_db():
    if not os.path.exists(DATABASE):
        print(f"Criando banco de dados em {DATABASE}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS estoque (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    data_cadastro TEXT NOT NULL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS consumo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    quantidade INTEGER NOT NULL,
                    data_consumo TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES estoque(id) ON DELETE CASCADE 
                    -- Added ON DELETE CASCADE for better data integrity
                )
            ''')
            conn.commit()
            print("Tabelas criadas.")
    else:
        print(f"Banco de dados {DATABASE} já existe.")
        # Optional: Add logic here to check/update schema if needed

# Função para formatar a data e a hora (filtro strftime)
def format_datetime(value):
    if value is None:
        return ""
    try:
        # Try parsing common formats, including ISO and potentially others if needed
        date_object = None
        try:
             date_object = datetime.fromisoformat(value)
        except ValueError:
             # Add other formats if necessary, e.g., '%Y-%m-%d'
             date_object = datetime.strptime(value, '%Y-%m-%d') 

        return date_object.strftime("%d/%m/%Y - %H:%M") if date_object else "Data Inválida"
    except (ValueError, TypeError):
        return "Data Inválida" # Catch potential errors

#Registrar o filtro no app
app.jinja_env.filters['strftime'] = format_datetime

# Rota principal - Exibe a página principal
@app.route('/')
def principal():
    return render_template('principal.html')

# Rota para exibir o estoque (HTML page)
@app.route('/estoque')
def estoque_page(): # Renamed to avoid conflict with API route
    try:
        conn = get_db_connection()
        # Fetch items ordered by name for consistent display
        itens = conn.execute('SELECT * FROM estoque ORDER BY nome').fetchall()
        conn.close()
        # Convert Row objects to dictionaries for easier template processing if needed
        # itens_list = [dict(row) for row in itens] 
        return render_template('estoque.html', itens=itens)
    except sqlite3.Error as e:
        # Log the error for server-side debugging
        app.logger.error(f'Erro ao acessar o banco de dados em /estoque: {str(e)}')
        # Return an error page or a JSON error for AJAX calls if appropriate
        # For now, returning a simple error message page might be okay
        return render_template('error.html', message=f'Erro ao carregar estoque: {str(e)}'), 500
        # Or if called via fetch expecting HTML:
        # return f"<h1>Erro ao carregar estoque</h1><p>{str(e)}</p>", 500

# *** NEW API ROUTE FOR STOCK DATA ***
@app.route('/api/estoque')
def get_estoque_data():
    """Returns current stock data as JSON."""
    try:
        conn = get_db_connection()
        itens = conn.execute('SELECT id, nome, quantidade FROM estoque ORDER BY nome').fetchall()
        conn.close()
        # Convert Row objects to a list of dictionaries for JSON serialization
        itens_list = [dict(row) for row in itens]
        return jsonify(itens_list)
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao acessar o banco de dados em /api/estoque: {str(e)}')
        return jsonify({'message': f'Erro ao buscar dados de estoque: {str(e)}'}), 500


# Rota para adicionar um novo item ao estoque
@app.route('/adicionar', methods=['POST'])
def adicionar():
    if not request.form.get('nome') or not request.form.get('quantidade') or not request.form.get('data_cadastro'):
         return jsonify({'message': 'Campos obrigatórios faltando (nome, quantidade, data_cadastro)'}), 400
    try:
        nome = request.form['nome']
        quantidade = int(request.form['quantidade'])
        # Ensure data_cadastro is handled correctly (it comes as YYYY-MM-DD from <input type="date">)
        data_cadastro_str = request.form['data_cadastro'] 
        # Optional: Validate date format if needed, but storing as text is flexible
        # datetime.strptime(data_cadastro_str, '%Y-%m-%d') # Example validation

        if quantidade < 0:
             return jsonify({'message': 'Quantidade não pode ser negativa'}), 400

        conn = get_db_connection()
        conn.execute('INSERT INTO estoque (nome, quantidade, data_cadastro) VALUES (?, ?, ?)', 
                       (nome.strip(), quantidade, data_cadastro_str)) # Use strip() for name
        conn.commit()
        conn.close()
        app.logger.info(f"Item '{nome}' adicionado com sucesso.")
        return jsonify({'message': 'Item adicionado com sucesso'}), 201 # 201 Created status
    except ValueError:
        return jsonify({'message': 'Quantidade inválida (deve ser um número inteiro)'}), 400
    except sqlite3.IntegrityError: # Example: If name had UNIQUE constraint
         return jsonify({'message': f'Erro: Item com nome "{nome}" talvez já exista'}), 409 # 409 Conflict
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao adicionar item: {str(e)}')
        return jsonify({'message': f'Erro de banco de dados ao adicionar item: {str(e)}'}), 500
    except Exception as e: # Catch unexpected errors
        app.logger.error(f'Erro inesperado em /adicionar: {str(e)}')
        return jsonify({'message': f'Erro inesperado no servidor'}), 500

# Rota para consumir uma unidade do estoque
# Changed to POST method
@app.route('/consumir/<int:item_id>', methods=['POST']) 
def consumir(item_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check current quantity first
        cursor.execute('SELECT quantidade FROM estoque WHERE id = ?', (item_id,))
        item = cursor.fetchone()

        if item is None:
             conn.close()
             return jsonify({'message': 'Item não encontrado'}), 404

        if item['quantidade'] <= 0:
            conn.close()
            return jsonify({'message': 'Item fora de estoque'}), 400 # Bad request - cannot consume 0

        # Update quantity
        cursor.execute('UPDATE estoque SET quantidade = quantidade - 1 WHERE id = ?', (item_id,))
        
        # Registra o consumo na tabela 'consumo'
        # Use UTC for consistency if deploying across timezones potentially
        data_consumo = datetime.now().isoformat(timespec='seconds') # Store with seconds precision
        cursor.execute('INSERT INTO consumo (item_id, quantidade, data_consumo) VALUES (?, ?, ?)', 
                       (item_id, 1, data_consumo))
        
        conn.commit()
        
        # Get updated quantity to return
        cursor.execute('SELECT quantidade FROM estoque WHERE id = ?', (item_id,))
        updated_item = cursor.fetchone()
        
        conn.close()
        app.logger.info(f"Item ID {item_id} consumido. Nova quantidade: {updated_item['quantidade']}")
        # Return updated quantity along with success message
        return jsonify({
            'message': 'Item consumido com sucesso', 
            'nova_quantidade': updated_item['quantidade'] if updated_item else 0
            }), 200 
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao consumir item ID {item_id}: {str(e)}')
        # Rollback changes if possible (though commit is usually at the end)
        try: 
           if conn: conn.rollback() 
        except: pass # Ignore rollback errors
        return jsonify({'message': f'Erro de banco de dados ao consumir item: {str(e)}'}), 500
    except Exception as e: # Catch unexpected errors
        app.logger.error(f'Erro inesperado em /consumir/{item_id}: {str(e)}')
        return jsonify({'message': f'Erro inesperado no servidor'}), 500
    finally:
        # Ensure connection is closed even if errors occur before conn.close()
        try:
            if conn and not conn.closed: conn.close()
        except: pass


# Rota para editar um item do estoque
@app.route('/editar/<int:item_id>', methods=['POST'])
def editar(item_id):
    if not request.form.get('nome') or not request.form.get('quantidade'):
         return jsonify({'message': 'Campos obrigatórios faltando (nome, quantidade)'}), 400
    try:
        nome = request.form['nome'].strip()
        quantidade = int(request.form['quantidade'])

        if not nome:
             return jsonify({'message': 'Nome não pode ser vazio'}), 400
        if quantidade < 0:
            return jsonify({'message': 'Quantidade não pode ser negativa'}), 400

        conn = get_db_connection()
        # Check if item exists before updating
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM estoque WHERE id = ?', (item_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'message': 'Item não encontrado para editar'}), 404

        conn.execute('UPDATE estoque SET nome = ?, quantidade = ? WHERE id = ?', (nome, quantidade, item_id))
        conn.commit()
        conn.close()
        app.logger.info(f"Item ID {item_id} editado para nome='{nome}', quantidade={quantidade}")
        return jsonify({'message': 'Item editado com sucesso'})
    except ValueError:
        return jsonify({'message': 'Quantidade inválida (deve ser um número inteiro)'}), 400
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao editar item ID {item_id}: {str(e)}')
        try: 
           if conn: conn.rollback() 
        except: pass
        return jsonify({'message': f'Erro de banco de dados ao editar item: {str(e)}'}), 500
    except Exception as e: # Catch unexpected errors
        app.logger.error(f'Erro inesperado em /editar/{item_id}: {str(e)}')
        return jsonify({'message': f'Erro inesperado no servidor'}), 500
    finally:
        try:
            if conn and not conn.closed: conn.close()
        except: pass


# Rota para excluir um item do estoque
@app.route('/excluir/<int:item_id>', methods=['POST']) # POST is safer than GET for deletion
def excluir_item(item_id):
    try:
        conn = get_db_connection()
         # Check if item exists before deleting
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM estoque WHERE id = ?', (item_id,))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'message': 'Item não encontrado para excluir'}), 404

        # Note: If you set up ON DELETE CASCADE for the foreign key in 'consumo', 
        # related consumption records will be deleted automatically. 
        # If not, you might want to delete them manually here first:
        # conn.execute('DELETE FROM consumo WHERE item_id = ?', (item_id,))
        
        conn.execute('DELETE FROM estoque WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        app.logger.info(f"Item ID {item_id} excluído com sucesso.")
        return jsonify({'message': 'Item excluido com sucesso'}) # Should be 'excluído'
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao excluir o item ID {item_id}: {str(e)}')
        try: 
           if conn: conn.rollback() 
        except: pass
        return jsonify({'message': f'Erro de banco de dados ao excluir o item: {str(e)}'}), 500
    except Exception as e: # Catch unexpected errors
        app.logger.error(f'Erro inesperado em /excluir/{item_id}: {str(e)}')
        return jsonify({'message': f'Erro inesperado no servidor'}), 500
    finally:
        try:
            if conn and not conn.closed: conn.close()
        except: pass


# Rota para exibir as estatísticas de consumo (HTML page)
@app.route('/estatisticas')
def estatisticas_page(): # Renamed
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Fetching data for display, including item name
        cursor.execute('''
            SELECT 
                e.nome,
                c.data_consumo,
                c.quantidade
            FROM consumo c
            JOIN estoque e ON c.item_id = e.id
            ORDER BY e.nome, c.data_consumo DESC -- Show recent consumption first per item
        ''')
        itens_consumo_raw = cursor.fetchall()
        conn.close()

        # Organizar os dados por item para o template
        dados_template = {}
        for item in itens_consumo_raw:
            nome_item = item['nome']
            if nome_item not in dados_template:
                dados_template[nome_item] = []
            dados_template[nome_item].append({
                # Keep original data format for display, rely on Jinja filter
                'data_consumo': item['data_consumo'], 
                'quantidade': item['quantidade']
                })

        return render_template('estatisticas.html', dados_grafico=dados_template)
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao acessar o banco de dados em /estatisticas: {str(e)}')
        return render_template('error.html', message=f'Erro ao carregar estatísticas: {str(e)}'), 500

# Rota para fornecer os dados de consumo para o modelo de ML (API endpoint)
@app.route('/api/consumo')
def get_consumo_data():
    """Returns consumption data grouped by item name as JSON."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                e.id as item_id, -- Include item_id if needed
                e.nome,
                c.data_consumo,
                c.quantidade
            FROM consumo c
            JOIN estoque e ON c.item_id = e.id
            ORDER BY e.nome, c.data_consumo ASC -- Order chronologically for time series analysis
        ''')
        itens_consumo_raw = cursor.fetchall()
        conn.close()

        # Organizar os dados por item name for JSON response
        dados_consumo_api = {}
        for item in itens_consumo_raw:
            nome_item = item['nome']
            if nome_item not in dados_consumo_api:
                dados_consumo_api[nome_item] = []
            dados_consumo_api[nome_item].append({
                'data_consumo': item['data_consumo'], # ISO format is good for JS
                'quantidade': item['quantidade']
                # Optionally include 'item_id': item['item_id'] if the ML model needs it
                })

        # print("Dados de consumo para API:", dados_consumo_api) # Debugging line
        return jsonify(dados_consumo_api)
    except sqlite3.Error as e:
        app.logger.error(f'Erro ao acessar o banco de dados em /api/consumo: {str(e)}')
        return jsonify({'message': f'Erro ao buscar dados de consumo: {str(e)}'}), 500

# Error handler for 404 Not Found
@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', message='Página não encontrada'), 404

# Error handler for 500 Internal Server Error
@app.errorhandler(500)
def internal_error(error):
    # You might want to log the actual error here
    app.logger.error(f'Server Error: {error}')
    return render_template('error.html', message='Erro interno no servidor'), 500

# Template for displaying errors (create templates/error.html)
# Example error.html:
# <!DOCTYPE html><html><head><title>Erro</title></head>
# <body><h1>Ocorreu um Erro</h1><p>{{ message }}</p>
# <a href="{{ url_for('principal') }}">Voltar para a página inicial</a></body></html>

if __name__ == '__main__':
    print("Inicializando o banco de dados...")
    init_db()  # Inicializa o banco de dados, caso não exista
    print("Iniciando a aplicação Flask...")
    # Use host='0.0.0.0' to make it accessible on your network if needed
    app.run(debug=True, host='127.0.0.1', port=5000) 
# --- END OF FILE app.py ---