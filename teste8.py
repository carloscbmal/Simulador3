import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io
import math
import os
import seaborn as sns
import matplotlib.pyplot as plt

# ==========================================
# CONFIGURAÇÕES E CONSTANTES
# ==========================================

HIERARQUIA = ['SD 1', 'CB', '3º SGT', '2º SGT', '1º SGT', 'SUB TEN', 
              '2º TEN', '1º TEN', 'CAP', 'MAJ', 'TEN CEL', 'CEL']

# Postos específicos para o Mapa de Calor conforme a imagem
POSTOS_MAPA = ['2º TEN', '1º TEN', 'CAP', 'MAJ', 'TEN CEL']

TEMPO_MINIMO = {
    'SD 1': 5, 'CB': 3, '3º SGT': 3, '2º SGT': 3, '1º SGT': 2,
    'SUB TEN': 2, '2º TEN': 3, '1º TEN': 3, 'CAP': 3, 'MAJ': 2, 'TEN CEL': 30
}

POSTOS_COM_EXCEDENTE = ['CB', '3º SGT', '2º SGT', '2º TEN', '1º TEN', 'CAP']

VAGAS_QOA = {
    'SD 1': 600, 'CB': 600, '3º SGT': 573, '2º SGT': 409, '1º SGT': 245,
    'SUB TEN': 96, '2º TEN': 34, '1º TEN': 29, 'CAP': 24, 'MAJ': 10, 'TEN CEL': 1, 'CEL': 9999
}

VAGAS_QOMT = {
    'SD 1': 30, 'CB': 30, '3º SGT': 30,
    '2º SGT': 68, '1º SGT': 49, 'SUB TEN': 19, 
    '2º TEN': 14, '1º TEN': 11, 'CAP': 8, 'MAJ': 4, 'TEN CEL': 2, 'CEL': 0
}

VAGAS_QOM = {
    'SD 1': 30, 'CB': 30,
    '3º SGT': 1, '2º SGT': 13, '1º SGT': 10, 'SUB TEN': 5, 
    '2º TEN': 11, '1º TEN': 9, 'CAP': 6, 'MAJ': 4, 'TEN CEL': 2, 'CEL': 0
}

# ==========================================
# FUNÇÕES DE LÓGICA
# ==========================================

def carregar_dados(nome_arquivo):
    if not os.path.exists(nome_arquivo):
        return None
    try:
        df = pd.read_excel(nome_arquivo)
        cols_numericas = ['Matricula', 'Pos_Hierarquica']
        for col in cols_numericas:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        cols_datas = ['Ultima_promocao', 'Data_Admissao', 'Data_Nascimento']
        for col in cols_datas:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], dayfirst=True)
        if 'Excedente' not in df.columns:
            df['Excedente'] = ""
        df['Excedente'] = df['Excedente'].fillna("")
        return df
    except Exception as e:
        st.error(f"Erro ao ler {nome_arquivo}: {e}")
        return None

def get_anos(data_ref, data_origem):
    if pd.isna(data_origem): return 0
    return relativedelta(data_ref, data_origem).years

def executar_simulacao_quadro(df_input, vagas_limite_base, data_alvo, tempo_aposentadoria, 
                              matriculas_foco, vagas_extras_dict=None):
    df = df_input.copy()
    data_atual = pd.to_datetime(datetime.now().strftime('%d/%m/%Y'), dayfirst=True)
    
    datas_ciclo = []
    for ano in range(data_atual.year, data_alvo.year + 1):
        for mes, dia in [(6, 26), (11, 29)]:
            d = pd.Timestamp(year=ano, month=mes, day=dia)
            if data_atual <= d <= data_alvo:
                datas_ciclo.append(d)
    datas_ciclo.sort()

    df_inativos = pd.DataFrame()
    sobras_por_ciclo = {}

    for data_referencia in datas_ciclo:
        sobras_deste_ciclo = {posto: 0 for posto in HIERARQUIA}
        extras_hoje = (vagas_extras_dict or {}).get(data_referencia, {})

        # A) PROMOÇÕES
        for i in range(len(HIERARQUIA) - 1):
            posto_atual = HIERARQUIA[i]
            proximo_posto = HIERARQUIA[i+1]
            candidatos = df[df['Posto_Graduacao'] == posto_atual].sort_values('Pos_Hierarquica')
            limite_atual = vagas_limite_base.get(proximo_posto, 9999) + extras_hoje.get(proximo_posto, 0)
            ocupados_reais = len(df[(df['Posto_Graduacao'] == proximo_posto) & (df['Excedente'] != "x")])
            vagas_disponiveis = limite_atual - ocupados_reais
            
            for idx, militar in candidatos.iterrows():
                anos_no_posto = relativedelta(data_referencia, militar['Ultima_promocao']).years
                if posto_atual in POSTOS_COM_EXCEDENTE and anos_no_posto >= 6:
                    df.at[idx, 'Posto_Graduacao'] = proximo_posto
                    df.at[idx, 'Ultima_promocao'] = data_referencia
                    df.at[idx, 'Excedente'] = "x"
                elif anos_no_posto >= TEMPO_MINIMO.get(posto_atual, 99) and vagas_disponiveis > 0:
                    df.at[idx, 'Posto_Graduacao'] = proximo_posto
                    df.at[idx, 'Ultima_promocao'] = data_referencia
                    df.at[idx, 'Excedente'] = ""
                    vagas_disponiveis -= 1

            if vagas_disponiveis > 0:
                sobras_deste_ciclo[proximo_posto] = int(vagas_disponiveis)
        
        sobras_por_ciclo[data_referencia] = sobras_deste_ciclo

        # B) ABSORÇÃO
        for posto in HIERARQUIA:
            limite_atual = vagas_limite_base.get(posto, 9999) + extras_hoje.get(posto, 0)
            vagas_abertas = limite_atual - len(df[(df['Posto_Graduacao'] == posto) & (df['Excedente'] != "x")])
            if vagas_abertas > 0:
                excedentes = df[(df['Posto_Graduacao'] == posto) & (df['Excedente'] == "x")].sort_values('Pos_Hierarquica')
                for idx_exc in excedentes.head(int(vagas_abertas)).index:
                    df.at[idx_exc, 'Excedente'] = ""

        # C) APOSENTADORIA
        idade = pd.to_numeric(df['Data_Nascimento'].apply(lambda x: get_anos(data_referencia, x)))
        servico = pd.to_numeric(df['Data_Admissao'].apply(lambda x: get_anos(data_referencia, x)))
        mask_apo = (idade >= 63) | (servico >= tempo_aposentadoria)
        
        if mask_apo.any():
            df_inativos = pd.concat([df_inativos, df[mask_apo].copy()], ignore_index=True)
            df = df[~mask_apo].copy()

    return df, df_inativos, {}, sobras_por_ciclo

# ==========================================
# INTERFACE
# ==========================================

def main():
    st.set_page_config(page_title="Mapa de Claros QOA", layout="wide")
    
    # Título igual ao da imagem
    st.title("🌡️ Mapa de Claros (Máximo de Vagas Ociosas por Ano)")

    df_militares = carregar_dados('militares.xlsx')
    df_condutores = carregar_dados('condutores.xlsx')
    df_musicos = carregar_dados('musicos.xlsx')

    if df_militares is None:
        st.error("Arquivo 'militares.xlsx' não encontrado.")
        return

    tempo_aposentadoria = 35
    data_alvo = datetime(2060, 12, 31)

    with st.spinner('Gerando simulação...'):
        # Simulações auxiliares para migração de vagas
        vagas_migradas = {}
        if df_condutores is not None:
            _, _, _, s_cond = executar_simulacao_quadro(df_condutores, VAGAS_QOMT, data_alvo, tempo_aposentadoria, [])
            for d, v in s_cond.items(): vagas_migradas[d] = v
        
        if df_musicos is not None:
            _, _, _, s_mus = executar_simulacao_quadro(df_musicos, VAGAS_QOM, data_alvo, tempo_aposentadoria, [])
            for d, v in s_mus.items():
                if d not in vagas_migradas: vagas_migradas[d] = {}
                for p, q in v.items():
                    mq = q if p in ['SD 1', 'CB', '3º SGT', '2º SGT', '1º SGT', 'SUB TEN'] else math.ceil(q/2)
                    vagas_migradas[d][p] = vagas_migradas[d].get(p, 0) + mq

        # Simulação principal QOA
        df_final, df_inativos, _, sobras_qoa = executar_simulacao_quadro(
            df_militares, VAGAS_QOA, data_alvo, tempo_aposentadoria, [], vagas_migradas
        )

    if sobras_qoa:
        dados_heatmap = []
        for d_ref, v_dict in sobras_qoa.items():
            for p, q in v_dict.items():
                if p in POSTOS_MAPA: # FILTRO SOLICITADO
                    dados_heatmap.append({'Ano': d_ref.year, 'Posto/Graduação': p, 'Vagas': q})
        
        df_h = pd.DataFrame(dados_heatmap)
        if not df_h.empty:
            # Pivot para colocar Postos no Eixo Y e Anos no Eixo X
            df_pivot = df_h.pivot_table(index='Posto/Graduação', columns='Ano', values='Vagas', aggfunc='max')
            
            # Reordenar o Eixo Y para seguir a hierarquia de cima para baixo (conforme imagem)
            df_pivot = df_pivot.reindex(reversed(POSTOS_MAPA))

            # Configuração Visual igual à imagem
            plt.style.use('default')
            fig, ax = plt.subplots(figsize=(18, 6))
            
            sns.heatmap(df_pivot, 
                        annot=True, 
                        fmt='.0f', 
                        cmap="Blues", 
                        linewidths=0, 
                        cbar_kws={'label': 'Qtd Vagas'},
                        ax=ax,
                        annot_kws={"weight": "bold"})
            
            ax.set_title("", pad=20)
            ax.set_xlabel("Ano da Promoção")
            ax.set_ylabel("Posto/Graduação")
            
            # Remove as bordas do gráfico para parecer o da imagem
            sns.despine(left=True, bottom=True)
            
            st.pyplot(fig)

            # Caixa de texto azul igual à imagem
            st.info("Os quadrados azuis indicam a presença de vagas ociosas (claros). Quanto mais escuro, maior o déficit.")
        else:
            st.warning("Nenhum dado de 'claros' encontrado para os postos selecionados até 2060.")

if __name__ == "__main__":
    main()
