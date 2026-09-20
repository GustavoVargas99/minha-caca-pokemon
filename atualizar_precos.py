import requests
from bs4 import BeautifulSoup
from datetime import datetime

TESTES = {
    "LigaPokemon": "https://www.ligapokemon.com.br/?view=cards/card&card=Charizard%20(RC5/83)&ed=GEN&num=RC5",
    "MYP Cards": "https://mypcards.com/"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

print("=" * 60)
print("MINHA CAÇA POKÉMON - TESTE DE ACESSO")
print("Executado em:", datetime.now())
print("=" * 60)

for nome, url in TESTES.items():
    print(f"\nTESTANDO: {nome}")
    print("URL:", url)

    try:
        resposta = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        print("STATUS HTTP:", resposta.status_code)
        print("TAMANHO:", len(resposta.text), "caracteres")

        soup = BeautifulSoup(resposta.text, "html.parser")

        if soup.title:
            print("TÍTULO:", soup.title.get_text(" ", strip=True))

        textos = soup.get_text(" ", strip=True)

        print("CONTÉM R$:", "R$" in textos)

        if resposta.status_code == 200:
            print("RESULTADO: ACESSO OK")
        else:
            print("RESULTADO: ACESSO NÃO CONFIRMADO")

    except Exception as erro:
        print("ERRO:", repr(erro))

print("\nTESTE FINALIZADO")
