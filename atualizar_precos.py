import requests
from bs4 import BeautifulSoup
import re

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

# Primeiro vamos descobrir como o MYP entrega resultados
# para o Charizard RC5 da nossa wishlist.
url = "https://mypcards.com/pokemon"

print("=" * 70)
print("MINHA CAÇA POKÉMON - TESTE DETALHADO MYP")
print("Carta: Charizard RC5 / Generations")
print("=" * 70)

sessao = requests.Session()
sessao.headers.update(headers)

try:
    resposta = sessao.get(url, timeout=30)

    print("STATUS:", resposta.status_code)
    print("URL FINAL:", resposta.url)
    print("TAMANHO:", len(resposta.text))

    soup = BeautifulSoup(resposta.text, "html.parser")

    print("\n--- TÍTULO ---")
    print(soup.title.get_text(" ", strip=True) if soup.title else "Sem título")

    print("\n--- FORMULÁRIOS ENCONTRADOS ---")

    formularios = soup.find_all("form")

    for numero, form in enumerate(formularios, 1):
        print(f"\nFORMULÁRIO {numero}")
        print("ACTION:", form.get("action"))
        print("METHOD:", form.get("method"))

        for campo in form.find_all(["input", "select"]):
            print(
                "CAMPO:",
                campo.name,
                "NAME=", campo.get("name"),
                "VALUE=", campo.get("value"),
                "PLACEHOLDER=", campo.get("placeholder")
            )

    print("\n--- LINKS COM CHARIZARD ---")

    encontrados = 0

    for link in soup.find_all("a", href=True):
        texto = link.get_text(" ", strip=True)
        href = link.get("href", "")

        if "charizard" in (texto + " " + href).lower():
            encontrados += 1
            print("\nTEXTO:", texto[:250])
            print("LINK:", href)

            pai = link.parent

            if pai:
                bloco = pai.get_text(" ", strip=True)
                precos = re.findall(
                    r"R\$\s*\d+(?:\.\d{3})*(?:,\d{2})?",
                    bloco
                )

                if precos:
                    print("PREÇOS NO BLOCO:", precos[:10])

            if encontrados >= 20:
                break

    print("\nTOTAL DE LINKS CHARIZARD MOSTRADOS:", encontrados)

    print("\n--- TEXTOS COM RC5 ---")

    texto_total = soup.get_text(" ", strip=True)

    posicao = texto_total.lower().find("rc5")

    if posicao >= 0:
        inicio = max(0, posicao - 500)
        fim = min(len(texto_total), posicao + 1000)

        print(texto_total[inicio:fim])
    else:
        print("RC5 não apareceu diretamente na página inicial.")

    print("\nTESTE CONCLUÍDO")

except Exception as erro:
    print("ERRO:", repr(erro))
    raise
