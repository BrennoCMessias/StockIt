# --- START OF FILE helper_module.py ---

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
# from xgboost import XGBRegressor # Descomente se for usar XGBoost
# from lightgbm import LGBMRegressor # Descomente se for usar LightGBM
import traceback # Para imprimir erros detalhados

def criar_features_temporais(df, lag_max=7, janela_movel=7):
    """
    Adiciona features temporais, de lag e de janela móvel a um DataFrame
    com índice de Datetime e uma coluna 'quantidade'.

    Args:
        df (pd.DataFrame): DataFrame com índice Datetime e coluna 'quantidade'.
                           Espera-se que já esteja agregado (e.g., por dia) e com fillna(0).
        lag_max (int): Número máximo de lags a serem criados.
        janela_movel (int): Tamanho da janela para calcular médias/std móveis.

    Returns:
        pd.DataFrame: DataFrame com as novas features. Retorna DataFrame vazio se entrada for vazia.
    """
    if df.empty:
        return pd.DataFrame() # Retorna vazio se não há dados

    df = df.copy()

    # Features baseadas na data
    df['dia_da_semana'] = df.index.dayofweek
    df['semana_do_ano'] = df.index.isocalendar().week.astype(int)
    df['mes'] = df.index.month
    df['dia_do_mes'] = df.index.day
    df['dia_do_ano'] = df.index.dayofyear
    df['ano'] = df.index.year

    # Features de Lag
    for lag in range(1, lag_max + 1):
        df[f'lag_{lag}'] = df['quantidade'].shift(lag)

    # Features de Janela Móvel
    df[f'media_movel_{janela_movel}d'] = df['quantidade'].shift(1).rolling(window=janela_movel, min_periods=1).mean()
    df[f'std_movel_{janela_movel}d'] = df['quantidade'].shift(1).rolling(window=janela_movel, min_periods=1).std()

    # Preencher NaNs iniciais (gerados por lag/rolling) com 0 ou outro valor
    # df = df.fillna(0) # Estratégia simples: preencher com 0
    # Ou remover linhas com NaNs (pode perder dados iniciais importantes)
    df = df.dropna()

    return df

def obter_previsao_sklearn(df_historico_consumo, dias_para_prever=7):
    """
    Obtém a previsão de consumo usando scikit-learn, recebendo os dados históricos.

    Args:
        df_historico_consumo (pd.DataFrame): DataFrame com colunas 'data_consumo' e 'quantidade'.
        dias_para_prever (int): Número de dias futuros a prever.

    Returns:
        dict: Dicionário contendo 'previsao', 'message', 'metodo'.
    """
    # item_id_debug = "N/A" # Para mensagens de erro, ID não é passado diretamente
    try:
        if df_historico_consumo.empty:
             return {'previsao': 0, 'message': 'Sem histórico de consumo.', 'metodo': 'N/A'}

        df = df_historico_consumo.copy()

        # --- CORREÇÃO APLICADA (Opção 1) ---
        try:
            # Tentar converter para datetime, inferindo o formato ISO8601
            # errors='coerce' transforma datas inválidas em NaT (Not a Time)
            df['data_consumo'] = pd.to_datetime(df['data_consumo'], format='ISO8601', errors='coerce')

            # Remover linhas onde a conversão falhou (se houver datas inválidas no DB)
            linhas_invalidas = df['data_consumo'].isna().sum()
            if linhas_invalidas > 0:
                 print(f"Alerta: Removidas {linhas_invalidas} linhas com datas inválidas durante a conversão.")
                 df = df.dropna(subset=['data_consumo'])

            # Se todas as datas eram inválidas ou o dataframe ficou vazio
            if df.empty:
                raise ValueError("Nenhuma data válida encontrada após a conversão.")

        except Exception as date_conv_error:
            print(f"Erro crítico ao converter 'data_consumo' para datetime: {date_conv_error}")
            traceback.print_exc()
            # Fallback para média histórica se a conversão de data falhar
            try:
                media_hist_fallback = df_historico_consumo['quantidade'].mean() * dias_para_prever
                media_hist_fallback = 0 if pd.isna(media_hist_fallback) else media_hist_fallback
            except Exception: # Caso df_historico_consumo também tenha problemas
                 media_hist_fallback = 0
            return {'previsao': round(media_hist_fallback, 2), 'message': f'Erro crítico na conversão de data ({date_conv_error}). Usando média histórica.', 'metodo': 'Média (Erro Conversão Data)'}
        # --- FIM DA CORREÇÃO ---

        df = df.set_index('data_consumo')

        # Agregar por dia e preencher dias sem consumo com 0
        df_diario = df['quantidade'].resample('D').sum().fillna(0)

        # --- Engenharia de Features ---
        lag_max = 7
        janela_movel = 7
        df_com_features = criar_features_temporais(df_diario.to_frame(), lag_max=lag_max, janela_movel=janela_movel) # Passa df_diario

        if df_com_features.empty or len(df_com_features) < 10: # Exige um mínimo de dados após criar features
             media_hist = df_diario.mean() * dias_para_prever
             media_hist = 0 if pd.isna(media_hist) else media_hist
             return {'previsao': round(media_hist, 2), 'message': 'Dados históricos insuficientes para modelo ML (após feature eng.). Usando média histórica.', 'metodo': 'Média Simples'}

        # --- Preparar para Treinamento ---
        X = df_com_features.drop('quantidade', axis=1)
        y = df_com_features['quantidade']

        # --- Escolher e Treinar o Modelo ---
        # Considerar ajustar hiperparâmetros se necessário
        modelo = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1, max_depth=10, min_samples_split=5)
        try:
            modelo.fit(X, y)
        except Exception as fit_error:
             print(f"Erro ao treinar modelo RandomForest: {fit_error}")
             traceback.print_exc()
             media_hist = df_diario.mean() * dias_para_prever
             media_hist = 0 if pd.isna(media_hist) else media_hist
             return {'previsao': round(media_hist, 2), 'message': f'Erro no treinamento do modelo ({fit_error}). Usando média.', 'metodo': 'Média (Erro Treino)'}

        # --- Previsão Iterativa para o Futuro ---
        previsoes_futuras_lista = []
        df_hist_features_recente = df_com_features.copy() # Começa com o histórico que tem features

        for i in range(dias_para_prever):
            # Preparar features para a próxima data
            ultima_data_hist = df_hist_features_recente.index.max()
            proxima_data = ultima_data_hist + pd.Timedelta(days=1)

            # Criar df temporário até a próxima data com placeholder
            # Usar apenas a coluna 'quantidade' para recalcular features
            df_temp_para_features = df_hist_features_recente[['quantidade']].copy()
            df_temp_para_features.loc[proxima_data] = 0 # Placeholder para a data a prever

            # Recalcular features para todo o conjunto temporário
            df_features_calculadas = criar_features_temporais(df_temp_para_features, lag_max=lag_max, janela_movel=janela_movel)

            # Verificar se o cálculo de features retornou algo (pode falhar se poucos dados)
            if df_features_calculadas.empty:
                print(f"Alerta: Cálculo de features para data futura {proxima_data} retornou vazio. Interrompendo previsão iterativa.")
                # Retornar a previsão acumulada até agora ou 0? Vamos retornar o acumulado.
                break # Sai do loop de previsão futura

            # Pegar apenas a linha da data que queremos prever
            features_proxima_data = df_features_calculadas.drop('quantidade', axis=1).tail(1)

            # Garantir colunas na ordem correta e que existem (preencher faltantes com 0)
            # Isso é crucial se o df_features_calculadas for mais curto que X.columns
            features_prontas_para_previsao = pd.DataFrame(0, index=features_proxima_data.index, columns=X.columns)
            # Copiar colunas existentes
            colunas_comuns = X.columns.intersection(features_proxima_data.columns)
            features_prontas_para_previsao[colunas_comuns] = features_proxima_data[colunas_comuns]

            # Fazer previsão
            previsao_dia = modelo.predict(features_prontas_para_previsao)[0]
            previsao_dia = max(0, round(previsao_dia, 4)) # Arredondar e garantir não negativo
            previsoes_futuras_lista.append(previsao_dia)

            # Atualizar o histórico com a previsão feita para a PRÓXIMA iteração
            novo_registro_hist = features_prontas_para_previsao.copy()
            novo_registro_hist['quantidade'] = previsao_dia # Adiciona a coluna 'quantidade' prevista
            novo_registro_hist.index = [proxima_data] # Define o índice correto

            # Concatenar ao histórico recente
            # Certificar-se de que as colunas estão alinhadas (pode precisar reordenar)
            df_hist_features_recente = pd.concat([df_hist_features_recente, novo_registro_hist[df_hist_features_recente.columns]]) # Garante mesmas colunas

        # --- Resultado Final ---
        previsao_total = sum(previsoes_futuras_lista)

        # Mensagem de sucesso mais informativa
        msg_sucesso = f'Previsão ({len(previsoes_futuras_lista)}/{dias_para_prever} dias) gerada com {type(modelo).__name__}.'
        if len(previsoes_futuras_lista) < dias_para_prever:
             msg_sucesso += " Previsão pode ser parcial devido a dados insuficientes para o período completo."


        return {'previsao': round(previsao_total, 2), 'message': msg_sucesso, 'metodo': type(modelo).__name__}

    except Exception as e:
        print(f"Erro GERAL não tratado ao obter previsão sklearn: {e}")
        traceback.print_exc()
        # Fallback final
        try:
             if not df_historico_consumo.empty:
                 media_geral = df_historico_consumo['quantidade'].mean() * dias_para_prever
                 media_geral = 0 if pd.isna(media_geral) else media_geral
             else: media_geral = 0
             return {'previsao': round(media_geral, 2), 'message': f'Erro crítico inesperado ({e}). Usando média histórica.', 'metodo': 'Média (Erro Crítico)'}
        except: # Se até a média falhar
             return {'previsao': 0, 'message': f'Erro crítico irrecuperável ({e}).', 'metodo': 'Erro'}

# --- END OF FILE helper_module.py ---