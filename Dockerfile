# Usa uma imagem oficial leve do Python
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia o arquivo de dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte para dentro do container
COPY main.py .

# Expõe a porta que a API vai rodar
EXPOSE 8000

# Comando para rodar o Uvicorn forcando 1 ÚNICO worker (--workers 1)
# Isso mantém a contagem de requisições centralizada na memória local
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
