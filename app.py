from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

DATABASE = 'database.db'

# Função para conectar ao banco de dados
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome
    return conn

# Função para inicializar o banco de dados, se ele não existir
def init_db():
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
        conn.commit()

# Rota principal - Exibe a página principal
@app.route('/')
def principal():
    return render_template('principal.html')

# Rota para exibir o estoque
@app.route('/estoque')
def estoque():
    try:
        conn = get_db_connection()
        itens = conn.execute('SELECT * FROM estoque').fetchall()
        conn.close()
        return render_template('estoque.html', itens=itens)
    except sqlite3.Error as e:
        return jsonify({'message': f'Erro ao acessar o banco de dados: {str(e)}'}), 500

# Rota para adicionar um novo item ao estoque
@app.route('/adicionar', methods=['POST'])
def adicionar():
    try:
        nome = request.form['nome']
        quantidade = int(request.form['quantidade'])
        data_cadastro = request.form['data_cadastro']

        conn = get_db_connection()
        conn.execute('INSERT INTO estoque (nome, quantidade, data_cadastro) VALUES (?, ?, ?)', (nome, quantidade, data_cadastro))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Item adicionado com sucesso'})  # Retorna JSON
    except ValueError:
        return jsonify({'message': 'Quantidade inválida'}), 400
    except sqlite3.Error as e:
        return jsonify({'message': f'Erro ao adicionar item: {str(e)}'}), 500

# Rota para consumir uma unidade do estoque
@app.route('/consumir/<int:item_id>')
def consumir(item_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE estoque SET quantidade = quantidade - 1 WHERE id = ? AND quantidade > 0', (item_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Item consumido com sucesso'})  # Retorna JSON
    except sqlite3.Error as e:
        return jsonify({'message': f'Erro ao consumir item: {str(e)}'}), 500

# Rota para editar um item do estoque
@app.route('/editar/<int:item_id>', methods=['POST'])
def editar(item_id):
    try:
        nome = request.form['nome']
        quantidade = int(request.form['quantidade'])

        conn = get_db_connection()
        conn.execute('UPDATE estoque SET nome = ?, quantidade = ? WHERE id = ?', (nome, quantidade, item_id))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Item editado com sucesso'})  # Retorna JSON
    except ValueError:
        return jsonify({'message': 'Quantidade inválida'}), 400
    except sqlite3.Error as e:
        return jsonify({'message': f'Erro ao editar item: {str(e)}'}), 500

# Rota para excluir um item do estoque
@app.route('/excluir/<int:item_id>', methods=['POST'])
def excluir_item(item_id):
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM estoque WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Item excluido com sucesso'})  # Retorna JSON
    except sqlite3.Error as e:
        return jsonify({'message': f'Erro ao excluir o item: {str(e)}'}), 500

if __name__ == '__main__':
    init_db()  # Inicializa o banco de dados, caso não exista
    app.run(debug=True)