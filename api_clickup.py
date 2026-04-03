import requests

# 1. Cole sua chave real aqui (começa com pk_)
MINHA_CHAVE = "pk_87366696_UG5ZRX6TF0WK4CEVS8WQR8MEWAAH6GQQ"

# 2. Montamos o cabeçalho exigido pelo ClickUp
headers = {
    "Authorization": MINHA_CHAVE,
    "Content-Type": "application/json"
}

# 3. Endpoint correto para listar seus Workspaces com Token Pessoal
url = "https://api.clickup.com/api/v2/team"

print("Enviando requisição para o ClickUp...")
response = requests.get(url, headers=headers)

# 4. Verificamos a resposta
if response.status_code == 200:
    print("\n✅ SUCESSO! A chave é válida. Aqui estão seus dados:")
    print(response.json())
else:
    print(f"\n🚨 ERRO {response.status_code}: {response.text}")