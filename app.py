import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Agente Jurídico IA", layout="wide")

# Configuração da Chave de API (Secrets do Streamlit)
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except Exception as e:
    st.error("⚠️ Chave de API não configurada. Adicione-a nos 'Secrets' do Streamlit Cloud.")
    
# --- DADOS E LÓGICA (BACK-END) ---

# 1. Base de Usuários (Simulação)
base_usuarios = {
    "junior": {"nome": "João Silva", "senha": "123", "cidades": ["São Paulo"], "permissoes": ["LER", "UPLOAD"]},
    "senior": {"nome": "Maria Costa", "senha": "456", "cidades": ["São Paulo", "Rio de Janeiro"], "permissoes": ["LER", "UPLOAD"]},
    "admin": {"nome": "Sócio Fundador", "senha": "admin", "cidades": ["TODAS"], "permissoes": ["LER", "UPLOAD", "DELETE"]}
}

# 2. Funções de IA e Dados
def consultar_advogado(pergunta, modelo_nome="gemini-2.5-flash"):
    model = genai.GenerativeModel(modelo_nome)
    prompt = f"""
    Atue como Advogado Sênior Especialista em Direito Municipal.
    Responda à pergunta com base no conhecimento jurídico geral (nesta versão demo):
    
    Pergunta: {pergunta}
    """
    return model.generate_content(prompt).text

# --- INTERFACE (FRONT-END) ---

# Título Principal
st.title("⚖️ Sistema de Inteligência Jurídica Municipal")

# Verifica se está logado
if 'usuario_logado' not in st.session_state:
    st.session_state['usuario_logado'] = None

# --- TELA DE LOGIN ---
if st.session_state['usuario_logado'] is None:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.header("🔐 Acesso Restrito")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        
        if st.button("Entrar"):
            user_data = base_usuarios.get(usuario)
            if user_data and user_data['senha'] == senha:
                st.session_state['usuario_logado'] = usuario
                st.session_state['dados_usuario'] = user_data
                st.rerun() # Recarrega a página
            else:
                st.error("Usuário ou senha incorretos")

# --- TELA DO SISTEMA (PÓS-LOGIN) ---
else:
    dados = st.session_state['dados_usuario']
    
    # BARRA LATERAL (Menu)
    with st.sidebar:
        st.info(f"👤 Olá, {dados['nome']}")
        
        # 1. Seletor de Cidade (Respeitando permissões)
        if "TODAS" in dados['cidades']:
            cidades_disponiveis = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba"]
        else:
            cidades_disponiveis = dados['cidades']
            
        cidade_selecionada = st.selectbox("📂 Selecione o Acervo:", cidades_disponiveis)
        st.divider()
        
        # 2. Área de Upload (Só aparece se tiver permissão)
        if "UPLOAD" in dados['permissoes']:
            st.subheader("⬆️ Enviar Nova Lei")
            arquivo = st.file_uploader("Solte o PDF aqui", type=["pdf"])
            if arquivo:
                # Aqui entraria aquela lógica de hash/duplicidade que criamos
                st.success(f"Arquivo '{arquivo.name}' enviado para análise!")
        
        st.divider()
        if st.button("Sair"):
            st.session_state['usuario_logado'] = None
            st.rerun()

    # ÁREA PRINCIPAL (Chat)
    st.subheader(f"💬 Consultor Jurídico - Base: {cidade_selecionada}")
    
    # Histórico de Chat (Memória visual)
    if "mensagens" not in st.session_state:
        st.session_state["mensagens"] = [{"role": "ai", "content": "Olá! Sou seu assistente jurídico. Qual dúvida deseja analisar no acervo hoje?"}]

    for msg in st.session_state["mensagens"]:
        st.chat_message(msg["role"]).write(msg["content"])

    # Campo de Pergunta
    if pergunta := st.chat_input("Ex: Qual a alíquota de ISS para serviços médicos?"):
        # Mostra pergunta do usuário
        st.session_state["mensagens"].append({"role": "user", "content": pergunta})
        st.chat_message("user").write(pergunta)
        
        # Gera resposta da IA
        with st.spinner("🧠 Analisando legislação e jurisprudência..."):
            resposta = consultar_advogado(pergunta)
        
        # Mostra resposta da IA
        st.session_state["mensagens"].append({"role": "ai", "content": resposta})
        st.chat_message("ai").write(resposta)
