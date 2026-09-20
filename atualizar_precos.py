import requests
from bs4 import BeautifulSoup
import re

URL = "https://mypcards.com/pokemon/produto/36248/charizard"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

print("=" * 70)
print("MINHA CAÇA POKÉMON - CONFERÊNCIA DOS ANÚNCIOS")
print("=" * 70)

r = requests.get(URL, headers=headers, timeout=30)

print("STATUS:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")

texto = soup.get_text(" ", strip=True)

# Procura trechos contendo conservação e preço.
padrao = re.compile(
    r"(DM|MP|SP|NM).*?R\$\s*([\d\.\,]+)",
    re.IGNORECASE
)

resultados = padrao.findall(texto)

print()
print("TOTAL DE COMBINAÇÕES ENCONTRADAS:", len(resultados))
print()

contagem = {}

for numero, (condicao, preco) in enumerate(resultados, start=1):

    condicao = condicao.upper()

    print("-" * 70)
    print("ANÚNCIO:", numero)
    print("CONSERVAÇÃO:", condicao)
    print("PREÇO: R$", preco)

    if condicao not in contagem:
        contagem[condicao] = 0

    contagem[condicao] += 1

print()
print("=" * 70)
print("CONTAGEM FINAL")
print("=" * 70)

for condicao in ["DM", "MP", "SP", "NM"]:
    print(condicao, ":", contagem.get(condicao, 0))

print()
print("TESTE FINALIZADO")
