import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Leis Municipal IA", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
def connect_to_sheets():
    try:
        # Pega as credenciais do cofre do Streamlit
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["connections"]["gsheets"]["creds"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("base_juridica_ia")
        return sheet
    except Exception as e:
        st.error(f"Erro ao conectar na planilha: {e}")
        return None

# --- FUNÇÕES DE SEGURANÇA E USUÁRIOS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def carregar_usuarios(sheet):
    worksheet = sheet.worksheet("usuarios")
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def registrar_usuario(sheet, nome, usuario, senha):
    worksheet = sheet.worksheet("usuarios")
    senha_hash = hash_password(senha)
    # Adiciona: username, password, name, cities, permissions, status
    worksheet.append_row([usuario, senha_hash, nome, "NENHUMA", "LER", "Pendente"])

def atualizar_usuario(sheet, usuario_alvo, nova_cidade, novo_status, nova_permissao):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    # Colunas: D=4 (Cidades), E=5 (Permissões), F=6 (Status)
    worksheet.update_cell(cell.row, 4, nova_cidade)
    worksheet.update_cell(cell.row, 5, nova_permissao)
    worksheet.update_cell(cell.row, 6, novo_status)

def alterar_senha_usuario(sheet, usuario_alvo, nova_senha):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    nova_senha_hash = hash_password(nova_senha)
    worksheet.update_cell(cell.row, 2, nova_senha_hash)

# --- CONFIGURAÇÃO GEMINI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("Configure a GOOGLE_API_KEY nos Secrets.")

# --- INTERFACE PRINCIPAL ---

sheet = connect_to_sheets()

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario_atual"] = {}
if "cidade_selecionada" not in st.session_state:
    st.session_state["cidade_selecionada"] = None

# TELA DE LOGIN / CADASTRO
if not st.session_state["logado"]:
    
    # --- AJUSTE VISUAL (TÍTULO + COPYRIGHT COLADOS) ---
    st.markdown("""
        <h1 style='margin-bottom: -15px;'>🏛️ Leis Municipal IA</h1>
        <small style='color: grey; font-size: 12px;'>© Lopes & Souto Advogados Associados</small>
        <hr style='margin-top: 5px; margin-bottom: 20px;'>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])

    with tab1: # Login
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if sheet:
                try:
                    df_users = carregar_usuarios(sheet)
                    user_match = df_users[df_users['username'] == usuario]
                    
                    if not user_match.empty:
                        stored_pass = str(user_match.iloc[0]['password'])
                        status = str(user_match.iloc[0]['status']) if 'status' in user_match.columns else 'Aprovado'
                        
                        if stored_pass == hash_password(senha):
                            if status == "Aprovado" or usuario == "admin":
                                st.session_state["logado"] = True
                                st.session_state["usuario_atual"] = user_match.iloc[0].to_dict()
                                st.rerun()
                            else:
                                st.warning("🔒 Seu cadastro ainda está pendente de aprovação.")
                        else:
                            st.error("Senha incorreta.")
                    else:
                        st.error("Usuário não encontrado.")
                except Exception as e:
                    st.error(f"Erro ao ler usuários: {e}")

    with tab2: # Cadastro
        novo_nome = st.text_input("Nome Completo")
        novo_user = st.text_input("Escolha um Usuário")
        nova_senha = st.text_input("Escolha uma Senha", type="password")
        if st.button("Solicitar Acesso"):
            if sheet:
                try:
                    df_users = carregar_usuarios(sheet)
                    if novo_user in df_users['username'].values:
                        st.error("Este usuário já existe.")
                    else:
                        registrar_usuario(sheet, novo_nome, novo_user, nova_senha)
                        st.success("Cadastro enviado! Aguarde aprovação.")
                except Exception as e:
                     st.error(f"Erro no cadastro: {e}")

# ÁREA INTERNA (LOGADO)
else:
    user = st.session_state["usuario_atual"]
    
    # BARRA LATERAL
    with st.sidebar:
        st.header(f"Olá, {user['name']}")
        st.caption(f"Perfil: {user.get('permissions', 'LER')}")
        
        # Lista de Cidades
        st.divider()
        st.subheader("📍 Seus Acessos")
        lista_cidades_raw = str(user.get('cities', '')).split(',')
        lista_cidades = [c.strip() for c in lista_cidades_raw if c.strip() != ""]
        
        if "TODAS" in user.get('cities', ''):
             st.info("🌍 Acesso Global (Todas as Cidades)")
             if len(lista_cidades) <= 1:
                 lista_cidades = ["São Paulo", "Rio de Janeiro", "Belo Horizonte"]
        else:
            for cidade in lista_cidades:
                st.write(f"• {cidade}")

        st.divider()
        if st.button("Sair"):
            st.session_state["logado"] = False
            st.session_state["cidade_selecionada"] = None
            st.rerun()

        # Alterar Senha
        with st.expander("🔑 Alterar Senha"):
            senha_atual = st.text_input("Senha Atual", type="password")
            nova_senha_1 = st.text_input("Nova Senha", type="password")
            nova_senha_2 = st.text_input("Confirmar", type="password")
            
            if st.button("Salvar"):
                if hash_password(senha_atual) == str(user['password']):
                    if nova_senha_1 == nova_senha_2 and nova_senha_1 != "":
                        alterar_senha_usuario(sheet, user['username'], nova_senha_1)
                        st.success("Senha alterada! Relogue.")
                        st.session_state["logado"] = False
                        st.rerun()
                    else:
                        st.error("Senhas não conferem.")
                else:
                    st.error("Senha atual errada.")
    
    # FLUXO DE SELEÇÃO DE CIDADE
    if not st.session_state["cidade_selecionada"]:
        st.title("Bem-vindo ao Sistema")
        st.info("👈 Confira seus acessos na barra lateral.")
        
        st.subheader("Com qual município deseja trabalhar agora?")
        escolha = st.selectbox("Selecione na lista:", lista_cidades)
        
        if st.button(f"Acessar Painel de {escolha}"):
            st.session_state["cidade_selecionada"] = escolha
            st.rerun()

    # PAINEL DA CIDADE
    else:
        cidade_atual = st.session_state["cidade_selecionada"]
        
        col_voltar, col_titulo = st.columns([1, 5])
        with col_voltar:
            if st.button("⬅ Trocar"):
                st.session_state["cidade_selecionada"] = None
                st.rerun()
        with col_titulo:
            st.title(f"🏛️ Painel: {cidade_atual}")
        
        # ESTATÍSTICAS
        st.markdown("### 📊 Acervo Digital")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Lei Orgânica", "0", help="Conectaremos na V4.0")
        col2.metric("Leis Complementares", "0", help="Conectaremos na V4.0")
        col3.metric("Leis Ordinárias", "0", help="Conectaremos na V4.0")
        col4.metric("Decretos", "0", help="Conectaremos na V4.0")
        
        with st.expander("📂 Visualizar Índice Completo"):
            st.write("A lista de arquivos aparecerá aqui após a integração com o Banco de Dados.")
            st.button("🖨️ Imprimir Relatório", disabled=True)

        st.divider()

        # ÁREA DE TRABALHO
        permissions = str(user.get('permissions', ''))
        
        tab_consulta, tab_gestao = st.tabs(["💬 Consultar IA", "📤 Gestão de Arquivos"])
        
        with tab_consulta:
            st.subheader(f"Assistente Jurídico de {cidade_atual}")
            prompt = st.chat_input(f"Pergunte sobre as leis de {cidade_atual}...")
            if prompt:
                with st.chat_message("user"):
                    st.write(prompt)
                with st.chat_message("assistant"):
                    st.write("🤖 Analisando...")
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(f"Contexto: Leis do município de {cidade_atual}. Pergunta do usuário: {prompt}")
                        st.write(response.text)
                    except Exception as e:
                        st.error(f"Erro na IA: {e}")

        with tab_gestao:
            if "UPLOAD" in permissions:
                st.write("Envie novos arquivos para a base desta cidade.")
                uploaded_file = st.file_uploader("Selecione o PDF", type="pdf")
                tipo_lei = st.selectbox("Tipo de Norma", ["Lei Ordinária", "Lei Complementar", "Decreto", "Lei Orgânica"])
                if uploaded_file and st.button("Salvar no Banco de Dados"):
                    st.success(f"Arquivo recebido! Na V4.0 ele será salvo na pasta de '{cidade_atual}'.")
            else:
                st.warning("Você não tem permissão para enviar arquivos.")
