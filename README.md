# StockIt - Controle de Despensa Inteligente (Flask App)

Uma aplicação web simples feita com Flask para gerenciamento de estoque de despensa,
incluindo cadastro, consumo, estatísticas e previsão básica de consumo
utilizando Machine Learning (Random Forest).

## Funcionalidades

*   Cadastro, edição e exclusão de itens no estoque.
*   Registro de consumo de itens.
*   Visualização do estoque atual.
*   Exibição de estatísticas de consumo por item.
*   Previsão de consumo semanal utilizando um modelo RandomForestRegressor.

## Tecnologias Utilizadas

*   Python 3
*   Flask
*   SQLite3
*   Pandas
*   Numpy
*   Scikit-learn
*   HTML / CSS / JavaScript (jQuery)
*   Font Awesome

## Configuração e Execução

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
    cd SEU_REPOSITORIO
    ```

2.  **Crie e ative um ambiente virtual (recomendado):**
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Execute a aplicação:**
    ```bash
    python app.py
    ```
    A aplicação estará disponível em `http://127.0.0.1:5000`.

5.  **Banco de Dados:** O banco de dados (`database.db`) será criado automaticamente na primeira execução, caso não exista.

## Estrutura do Projeto
Markdown
/
|-- app.py # Arquivo principal da aplicação Flask
|-- helper_module.py # Módulo com a lógica de previsão ML
|-- database.db # (IGNORADO PELO GIT) Arquivo do banco de dados SQLite
|-- requirements.txt # Dependências Python
|-- .gitignore # Arquivos e pastas ignorados pelo Git
|-- README.md # Este arquivo
|-- static/ # Arquivos estáticos (CSS, JS futuro, imagens)
| -- styles.css-- templates/ # Templates HTML (Jinja2)
|-- principal.html
|-- estoque.html
|-- estatisticas.html
`-- error.html