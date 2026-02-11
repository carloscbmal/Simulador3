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

# ALTERAÇÃO: Adicionado 1º SGT e removido CEL
POSTOS_MAPA = ['1º SGT', 'SUB TEN', '2º TEN', '1º TEN', 'CAP', 'MAJ', 'TEN CEL']

TEMPO_MINIMO = {
    'SD 1': 5, 'CB': 3, '3º SGT': 3, '2º SGT': 3, '1º SGT': 2,
    'SUB TEN': 2, '2º TEN': 3, '1º TEN': 3, 'CAP': 3, 'MAJ': 2, 'TEN CEL': 30
}

POSTOS_COM_EXCEDENTE = ['CB', '3º SGT', '2º SGT', '2º TEN', '1º TEN', 'CAP']

VAGAS_QOA = {
    'SD 1': 534, 'CB': 507, '3º SGT': 463, '2º SGT': 341, '1º SGT': 245,
    'SUB TEN': 96, '2º TEN': 34, '1º TEN': 29, 'CAP': 24, 'MAJ': 10, 'TEN CEL': 3, 'CEL': 9999
}

VAGAS_QOMT = {
    'SD 1': 107, 'CB': 101, '3º SGT': 93,
    '2º SGT': 68, '1º SGT': 49, 'SUB TEN': 19, 
    '2º TEN': 14, '1º TEN': 11, 'CAP': 8, 'MAJ': 4, 'TEN CEL': 2, 'CEL': 0
}

VAGAS_QOM = {
    'SD 1': 20, 'CB': 19,
    '3º SGT': 17, '2º SGT': 13, '1º SGT': 10, 'SUB TEN': 5, 
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
    vagas_abertas_log = {} 

    for data_referencia in datas_ciclo:
        extras_hoje = (vagas_extras_dict or {}).get(data_referencia, {})

        # PASSO 1: CALCULAR VAGAS ABERTAS (SNAPSHOT)
        snapshot_vagas = {}
        for posto in HIERARQUIA:
            limite_atual = vagas_limite_base.get(posto, 9999) + extras_hoje.get(posto, 0)
            ocupados_reais = len(df[(df['Posto_Graduacao'] == posto) & (df['Excedente'] != "x")])
            vagas = max(0, limite_atual - ocupados_reais)
            snapshot_vagas[posto] = int(vagas)
        
        vagas_abertas_log[data_referencia] = snapshot_vagas

        # PASSO 2: PROMOÇÕES
        for i in range(len(HIERARQUIA) - 1):
            posto_atual = HIERARQUIA[i]
            proximo_posto = HIERARQUIA[i+1]
            
            limite_atual = vagas_limite_base.get(proximo_posto, 9999) + extras_hoje.get(proximo_posto, 0)
            ocupados_reais = len(df[(df['Posto_Graduacao'] == proximo_posto) & (df['Excedente'] != "x")])
            vagas_disponiveis = limite_atual - ocupados_reais

            candidatos = df[df['Posto_Graduacao'] == posto_atual].sort_values('Pos_Hierarquica')
            
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

        # PASSO 3: ABSORÇÃO
        for posto in HIERARQUIA:
            limite_atual = vagas_limite_base.get(posto, 9999) + extras_hoje.get(posto, 0)
            ocupados_normais = len(df[(df['Posto_Graduacao'] == posto) & (df['Excedente'] != "x")])
            vagas_abertas = limite_atual - ocupados_normais
            
            if vagas_abertas > 0:
                excedentes = df[(df['Posto_Graduacao'] == posto) & (df['Excedente'] == "x")].sort_values('Pos_Hierarquica')
                for idx_exc in excedentes.head(int(vagas_abertas)).index:
                    df.at[idx_exc, 'Excedente'] = ""

        # PASSO 4: APOSENTADORIA
        idade = pd.to_numeric(df['Data_Nascimento'].apply(lambda x: get_anos(data_referencia, x)))
        servico = pd.to_numeric(df['Data_Admissao'].apply(lambda x: get_anos(data_referencia, x)))
        mask_apo = (idade >= 63) | (servico >= tempo_aposentadoria)
        
        if mask_apo.any():
            df_inativos = pd.concat([df_inativos, df[mask_apo].copy()], ignore_index=True)
            df = df[~mask_apo].copy()

    return df, df_inativos, {}, vagas_abertas_log

# ==========================================
# INTERFACE
# ==========================================

def main():
    st.set_page_config(page_title="Vagas Promoção QOA", layout="wide")
    
    st.title("📊 Disponibilidade de Vagas para Promoção (De 1º SGT a TEN CEL)")
    st.markdown("Visualize quantas vagas estarão abertas **na data oficial da promoção**, antes do processamento das mesmas.")

    df_militares = carregar_dados('militares.xlsx')
    df_condutores = carregar_dados('condutores.xlsx')
    df_musicos = carregar_dados('musicos.xlsx')

    if df_militares is None:
        st.error("Arquivo 'militares.xlsx' não encontrado.")
        return

    tempo_aposentadoria = 35
    data_alvo = datetime(2035, 12, 31) 

    with st.spinner('Gerando simulação de vagas...'):
        vagas_migradas = {}
        if df_condutores is not None:
            _, _, _, s_cond = executar_simulacao_quadro(df_condutores, VAGAS_QOMT, data_alvo, tempo_aposentadoria, [])
            for d, v in s_cond.items(): vagas_migradas[d] = v
        
        if df_musicos is not None:
            _, _, _, s_mus = executar_simulacao_quadro(df_musicos, VAGAS_QOM, data_alvo, tempo_aposentadoria, [])
            for d, v in s_mus.items():
                if d not in vagas_migradas: vagas_migradas[d] = {}
                for p, q in v.items():
                    mq = q if p in HIERARQUIA[:6] else math.ceil(q/2)
                    vagas_migradas[d][p] = vagas_migradas[d].get(p, 0) + mq

        df_final, df_inativos, _, log_vagas = executar_simulacao_quadro(
            df_militares, VAGAS_QOA, data_alvo, tempo_aposentadoria, [], vagas_migradas
        )

    if log_vagas:
        dados_heatmap = []
        for d_ref, v_dict in log_vagas.items():
            nome_data = d_ref.strftime('%d/%m/%y')
            for p, q in v_dict.items():
                if p in POSTOS_MAPA: # Filtro aplicado
                    dados_heatmap.append({'Data': nome_data, 'Posto/Graduação': p, 'Vagas': q})
        
        df_h = pd.DataFrame(dados_heatmap)
        
        if not df_h.empty:
            df_pivot = df_h.pivot_table(index='Posto/Graduação', columns='Data', values='Vagas', sort=False)
            
            # Reordenar eixo Y conforme POSTOS_MAPA invertido (para o mais alto ficar em cima)
            df_pivot = df_pivot.reindex(reversed(POSTOS_MAPA))
            
            datas_ordenadas = [d.strftime('%d/%m/%y') for d in sorted(log_vagas.keys())]
            datas_ordenadas = [d for d in datas_ordenadas if d in df_pivot.columns]
            df_pivot = df_pivot[datas_ordenadas]

            plt.style.use('default')
            largura_fig = max(10, len(datas_ordenadas) * 0.4)
            fig, ax = plt.subplots(figsize=(largura_fig, 6))
            
            # ALTERAÇÃO: cmap="Blues"
            sns.heatmap(df_pivot, 
                        annot=True, 
                        fmt='.0f', 
                        cmap="Blues", 
                        linewidths=0.5, 
                        linecolor='white',
                        cbar_kws={'label': 'Vagas Disponíveis'},
                        ax=ax,
                        annot_kws={"size": 9, "weight": "bold"})
            
            ax.set_title("Vagas Disponíveis por Data Oficial de Promoção", pad=20, fontsize=14)
            ax.set_xlabel("Data do Ciclo", fontsize=12)
            ax.set_ylabel("Posto/Graduação", fontsize=12)
            
            plt.xticks(rotation=45, ha='right')
            
            st.pyplot(fig)

            st.info("Nota: Os valores representam as vagas existentes (Limite - Ocupados) no início do dia da promoção.")
        else:
            st.warning("Nenhum dado encontrado para os postos selecionados.")

if __name__ == "__main__":
    main()
