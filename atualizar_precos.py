import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://mypcards.com"
INDEX = Path("index.html")
SAIDA = Path("precos.json")
CHECKPOINT = Path("precos_checkpoint.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)
CONDICOES = ("NM", "SP", "MP", "DM")

# Ritmo propositalmente conservador para não bombardear o MYP Cards.
INTERVALO_REQUISICAO = 2.5
MAX_TENTATIVAS = 5
MAX_LINKS = 8
ultima_requisicao = 0.0


class BloqueioTemporario(RuntimeError):
    pass


def brl(v):
    return float(v.replace(".", "").replace(",", "."))


def requisitar(url):
    """GET com espaçamento global e backoff progressivo para 429/5xx."""
    global ultima_requisicao
    ultimo_erro = None
    for tentativa in range(MAX_TENTATIVAS):
        decorrido = time.monotonic() - ultima_requisicao
        espera = INTERVALO_REQUISICAO - decorrido
        if espera > 0:
            time.sleep(espera + random.uniform(0.15, 0.65))

        try:
            r = session.get(url, timeout=35)
            ultima_requisicao = time.monotonic()
        except requests.RequestException as e:
            ultimo_erro = e
            pausa = min(15 * (2 ** tentativa), 180)
            print(f"    conexão falhou; aguardando {pausa}s ({tentativa + 1}/{MAX_TENTATIVAS})")
            time.sleep(pausa)
            continue

        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            try:
                pausa = int(retry_after) if retry_after else 30 * (2 ** tentativa)
            except ValueError:
                pausa = 30 * (2 ** tentativa)
            pausa = min(max(pausa, 30), 300)
            print(f"    MYP limitou as consultas (429); aguardando {pausa}s ({tentativa + 1}/{MAX_TENTATIVAS})")
            time.sleep(pausa + random.uniform(1, 4))
            ultimo_erro = BloqueioTemporario("HTTP 429")
            continue

        if 500 <= r.status_code < 600:
            pausa = min(15 * (2 ** tentativa), 180)
            print(f"    MYP respondeu {r.status_code}; aguardando {pausa}s")
            time.sleep(pausa)
            ultimo_erro = RuntimeError(f"HTTP {r.status_code}")
            continue

        r.raise_for_status()
        return r

    raise BloqueioTemporario(f"MYP indisponível após {MAX_TENTATIVAS} tentativas: {ultimo_erro}")


def carregar_cartas():
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"const\s+cards\s*=\s*(\[.*?\]);\s*\n", html, re.S)
    if not m:
        raise RuntimeError("Não encontrei const cards=[...] no index.html")
    return json.loads(m.group(1))


def chave_carta(carta):
    return "|".join(str(carta.get(k, "")).strip() for k in ("group", "name", "num", "img"))


def termos_busca(carta):
    nome = carta.get("name", "").strip()
    num = carta.get("num", "").strip()
    termos = [nome]
    if num and re.search(r"\d", num):
        termos.insert(0, f"{nome} {num}")
    simples = re.sub(r"\s*\([^)]*\)\s*", " ", nome).strip()
    if simples and simples not in termos:
        termos.append(simples)
    return list(dict.fromkeys(termos))


def buscar_links_myp(termo, limite=MAX_LINKS):
    url = f"{BASE}/pokemon?ProdutoSearch%5Bquery%5D={quote_plus(termo)}&ProdutoSearch%5BexibirSomenteVenda%5D=1"
    r = requisitar(url)
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.select('a[href*="/pokemon/produto/"]'):
        href = a.get("href")
        if href:
            full = urljoin(BASE, href.split("?")[0])
            if full not in links:
                links.append(full)
        if len(links) >= limite:
            break
    return links


def extrair_anuncios(url):
    r = requisitar(url)
    soup = BeautifulSoup(r.text, "html.parser")
    titulo = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1txt = h1.get_text(" ", strip=True) if h1 else ""
    texto = soup.get_text(" ", strip=True)
    padrao = re.compile(r"\b(NM|SP|MP|DM)\b.{0,260}?R\$\s*([\d\.]+,\d{2})", re.I | re.S)
    anuncios = []
    for cond, preco in padrao.findall(texto):
        try:
            valor = brl(preco)
        except ValueError:
            continue
        if 0 < valor < 1000000:
            anuncios.append({"condicao": cond.upper(), "preco": valor, "url": url})
    return {"url": url, "titulo": titulo, "h1": h1txt, "anuncios": anuncios}


def compatibilidade(carta, produto):
    alvo_nome = carta.get("name", "").lower()
    alvo_num = carta.get("num", "").lower()
    texto = (produto.get("titulo", "") + " " + produto.get("h1", "")).lower()
    pokemon = alvo_nome.split()[0] if alvo_nome else ""
    if pokemon and pokemon not in texto:
        return False
    nums = re.findall(r"\d+", alvo_nome + " " + alvo_num)
    nums_prod = set(re.findall(r"\d+", texto))
    if nums and any(n in nums_prod for n in nums):
        return True
    palavras = [p for p in re.findall(r"[a-z0-9]+", alvo_nome) if len(p) > 2]
    return bool(palavras) and sum(p in texto for p in palavras) >= min(2, len(palavras))


def escolher(anuncios):
    por = {c: [] for c in CONDICOES}
    for a in anuncios:
        if a["condicao"] in por:
            por[a["condicao"]].append(a)
    for c in por:
        por[c].sort(key=lambda x: x["preco"])
    principais = sorted(por["NM"] + por["SP"], key=lambda x: x["preco"])
    return {
        "melhor_nm_sp": principais[0] if principais else None,
        "menor_por_condicao": {c: (por[c][0] if por[c] else None) for c in CONDICOES},
        "mp_dm_para_analisar": por["MP"][:3] + por["DM"][:3],
        "total_anuncios": sum(len(v) for v in por.values()),
    }


def processar(carta):
    links = []
    bloqueado = False
    for termo in termos_busca(carta):
        try:
            for link in buscar_links_myp(termo):
                if link not in links:
                    links.append(link)
        except BloqueioTemporario as e:
            print("  busca temporariamente bloqueada:", termo, e)
            bloqueado = True
            break
        except Exception as e:
            print("  busca falhou:", termo, e)
        if len(links) >= MAX_LINKS:
            break

    if bloqueado and not links:
        raise BloqueioTemporario("consulta da carta não pôde ser confirmada")

    produtos, anuncios = [], []
    for link in links[:MAX_LINKS]:
        try:
            p = extrair_anuncios(link)
            if compatibilidade(carta, p):
                produtos.append({"url": p["url"], "titulo": p["titulo"], "h1": p["h1"]})
                anuncios.extend(p["anuncios"])
        except BloqueioTemporario:
            bloqueado = True
            print("  produto temporariamente bloqueado; interrompendo esta carta")
            break
        except Exception as e:
            print("  produto falhou:", link, e)

    if bloqueado:
        raise BloqueioTemporario("resultado incompleto por limitação temporária do MYP")

    resultado = escolher(anuncios)
    resultado.update({
        "grupo": carta.get("group"), "nome": carta.get("name"), "numero": carta.get("num"),
        "imagem_referencia": carta.get("img"), "fonte_prioritaria": "MYP Cards",
        "produtos_compativeis": produtos,
    })
    return resultado


def salvar(saida, checkpoint=True):
    saida["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    destino = CHECKPOINT if checkpoint else SAIDA
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_checkpoint():
    if not CHECKPOINT.exists():
        return None
    try:
        dados = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        if isinstance(dados.get("cartas"), list):
            return dados
    except Exception:
        pass
    return None


def main():
    cartas = carregar_cartas()
    print("=" * 72)
    print("MINHA CAÇA POKÉMON - ATUALIZAÇÃO GERAL MYP CARDS")
    print("Cartas no catálogo:", len(cartas))
    print("=" * 72)

    saida = carregar_checkpoint() or {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "regra": "Prioridade MYP; menor entre NM/SP; MP/DM separados para análise; mesma arte pode ser outra edição/idioma.",
        "cartas": []
    }
    prontas = {r.get("_chave") for r in saida["cartas"] if r.get("_chave") and not r.get("erro_temporario")}
    if prontas:
        print(f"Retomando checkpoint: {len(prontas)} cartas já concluídas.")

    for i, carta in enumerate(cartas, 1):
        chave = chave_carta(carta)
        if chave in prontas:
            print(f"[{i}/{len(cartas)}] já concluída - {carta.get('name')} {carta.get('num', '')}")
            continue

        print(f"[{i}/{len(cartas)}] {carta.get('name')} {carta.get('num', '')}")
        try:
            r = processar(carta)
            r["_chave"] = chave
            saida["cartas"] = [x for x in saida["cartas"] if x.get("_chave") != chave]
            saida["cartas"].append(r)
            melhor = r.get("melhor_nm_sp")
            print("  ->", f"{melhor['condicao']} R$ {melhor['preco']:.2f}" if melhor else "sem NM/SP confirmado")
            salvar(saida, checkpoint=True)
        except BloqueioTemporario as e:
            print("  PAUSA SEGURA:", e)
            print("  Progresso salvo. Execute novamente mais tarde; continuará das cartas pendentes.")
            salvar(saida, checkpoint=True)
            return
        except Exception as e:
            print("  ERRO:", e)
            saida["cartas"] = [x for x in saida["cartas"] if x.get("_chave") != chave]
            saida["cartas"].append({
                "_chave": chave, "grupo": carta.get("group"), "nome": carta.get("name"),
                "numero": carta.get("num"), "erro": str(e), "melhor_nm_sp": None
            })
            salvar(saida, checkpoint=True)

    # Só publica o arquivo definitivo quando todas as cartas terminarem.
    salvar(saida, checkpoint=False)
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()
    print("=" * 72)
    print("precos.json atualizado com sucesso.")


if __name__ == "__main__":
    main()
