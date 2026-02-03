import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- CONFIGURAÇÃO DA PÁGINA (PEDIDO 1: NOME NO NAVEGADOR) ---
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

# (PEDIDO 3: NOVA FUNÇÃO PARA TROCAR SENHA)
def alterar_senha_usuario(sheet, usuario_alvo, nova_senha):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    nova_senha_hash = hash_password(nova_senha)
    # Coluna B (2) é a senha
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

# TELA DE LOGIN / CADASTRO
if not st.session_state["logado"]:
    # (PEDIDO 1: NOME NA TELA DE LOGIN)
    st.title("🏛️ Leis Municipal IA")
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
        st.write(f"Olá, **{user['name']}**")
        st.write(f"Permissão: `{user.get('permissions', 'LER')}`")
        
        # (PEDIDO 3: BOTÃO DE ALTERAR SENHA)
        with st.expander("🔑 Alterar Senha"):
            senha_atual = st.text_input("Senha Atual", type="password")
            nova_senha_1 = st.text_input("Nova Senha", type="password")
            nova_senha_2 = st.text_input("Confirmar Nova Senha", type="password")
            
            if st.button("Salvar Nova Senha"):
                # Verifica senha atual
                if hash_password(senha_atual) == str(user['password']):
                    if nova_senha_1 == nova_senha_2 and nova_senha_1 != "":
                        alterar_senha_usuario(sheet, user['username'], nova_senha_1)
                        st.success("Senha alterada! Faça login novamente.")
                        st.session_state["logado"] = False
                        st.rerun()
                    else:
                        st.error("As novas senhas não coincidem.")
                else:
                    st.error("A senha atual está incorreta.")

        st.divider()
        if st.button("Sair"):
            st.session_state["logado"] = False
            st.rerun()
    
    # ÁREA DO ADMIN
    permissions = str(user.get('permissions', ''))
    if "DELETE" in permissions or user['username'] == 'admin':
        with st.expander("👮 Painel de Gestão (Admin)", expanded=False):
            if sheet:
                df_users = carregar_usuarios(sheet)
                lista_usuarios = df_users['username'].tolist()
                edit_user = st.selectbox("Editar Usuário", lista_usuarios)
                
                if edit_user:
                    user_data = df_users[df_users['username'] == edit_user].iloc[0]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        current_status = user_data.get('status', 'Pendente')
                        st_opts = ["Pendente", "Aprovado", "Bloqueado"]
                        new_status = st.selectbox("Status", st_opts, index=st_opts.index(current_status) if current_status in st_opts else 0)
                    with col2:
                        new_city = st.text_input("Cidades", value=user_data.get('cities', ''))
                    with col3:
                        p_opts = ["LER", "LER,UPLOAD", "LER,UPLOAD,DELETE"]
                        current_perm = user_data.get('permissions', 'LER')
                        new_perm = st.selectbox("Nível", p_opts, index=p_opts.index(current_perm) if current_perm in p_opts else 0)
                    
                    if st.button("Atualizar Usuário"):
                        atualizar_usuario(sheet, edit_user, new_city, new_status, new_perm)
                        st.success("Usuário atualizado!")
                        st.rerun()

    # ÁREA PRINCIPAL
    st.divider()
    # (PEDIDO 2: TEXTO "NORMAS")
    cidades_permitidas = user.get('cities', 'Nenhuma')
    st.subheader(f"Normas: {cidades_permitidas}")
    
    if "UPLOAD" in permissions:
        uploaded_file = st.file_uploader("Enviar nova Lei (PDF)", type="pdf")
        if uploaded_file:
            st.success("Arquivo recebido temporariamente.")

    prompt = st.chat_input("Pergunte sobre as leis municipais...")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            st.write("🤖 Analisando...")
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(f"O usuário perguntou: {prompt}. Responda como assistente jurídico.")
                st.write(response.text)
            except Exception as e:
                st.error(f"Erro na IA: {e}")
