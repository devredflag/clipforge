# ✂ ClipForge

Transforma vídeos e **lives** do YouTube em **cortes verticais (9:16) com legendas automáticas** e publica em
sequência (**Parte 1, Parte 2, …**) no **YouTube Shorts** e no **TikTok**, em horários definidos, todos os dias.

É um **aplicativo de desktop**: abre numa janela própria (com o servidor embutido), sem terminal. Há duas
formas de rodar — escolha uma:

- **A) Um clique (mais fácil, recomendado):** use o atalho **Iniciar-ClipForge** do seu sistema. Na primeira
  vez ele se prepara sozinho (precisa de Python e internet) e abre a janela do app. Nas próximas, abre direto.
- **B) Executável único (.exe/.app):** gere um aplicativo independente com os scripts em `packaging/` e depois
  é só dar duplo clique — não precisa de Python nem instalar nada. Veja **“Gerar o executável”** abaixo.

São duas peças que trabalham juntas:

- **App (backend + painel web)** — roda no seu computador. Baixa o vídeo, transcreve, escolhe os melhores
  trechos, corta em 9:16 com legenda e cuida da fila de publicação.
- **Extensão do Chrome** — coloca um botão **“✂ Cortar com ClipForge”** na página do vídeo/live do YouTube e
  tem um popup para colar links. Ela só manda o link para o app.

```
Chrome (extensão)  ──link──▶  App (backend)  ──▶  download → transcrição → cortes + legendas
                                   │
                                   └──▶  fila diária ──▶  YouTube Shorts + TikTok (Parte 1, 2, 3…)
```

---

## ⚠️ Antes de tudo: regras das plataformas (leia)

- **Use apenas conteúdo seu ou autorizado.** Baixar e repostar vídeos/lives de terceiros viola os Termos do
  YouTube e pode gerar strikes de direitos autorais e banimento das suas contas. O ClipForge não contorna
  nada disso — ele só automatiza o trabalho sobre o **seu** material.
- **YouTube:** projetos novos do Google Cloud **sem auditoria** publicam todo vídeo como **privado**, mesmo
  pedindo “público”. Para publicar público de verdade é preciso passar pela *YouTube API Compliance Audit*.
  A cota padrão também limita a poucos envios por dia até o aumento ser aprovado.
- **TikTok:** enquanto seu app **não passa pela auditoria** do TikTok, a publicação direta só aceita
  privacidade **SELF_ONLY** (o vídeo fica visível só para você). Dá para testar tudo assim; para público,
  peça a auditoria no portal. Alternativa: modo **inbox**, em que o vídeo chega como rascunho no app do
  TikTok e você toca em “Publicar”.

Nada disso impede você de montar e testar o sistema inteiro hoje — só muda a visibilidade final dos posts.

---

## 1. Abrir o app

### Forma A — Um clique

1. **Windows:** dê duplo clique em **`Iniciar-ClipForge.bat`**.
   **Mac/Linux:** dê duplo clique em **`Iniciar-ClipForge.command`** (no Mac, se o sistema bloquear, clique com
   o botão direito → Abrir na primeira vez).
2. Na primeira execução ele cria o ambiente e baixa as dependências (precisa de **Python 3.10+** instalado e de
   internet). Ao final, a **janela do ClipForge** abre sozinha. Nas próximas vezes, abre em segundos.

> Python: instale em [python.org/downloads](https://www.python.org/downloads/). No Windows, marque
> **“Add Python to PATH”** durante a instalação.

### Forma B — Executável único (sem Python) ⭐

Um único **`ClipForge.exe`** (Windows) que, ao dar duplo clique, faz tudo sozinho — sem Python, sem instalar
nada. A maneira mais fácil de obtê-lo **sem compilar no seu PC** é pelo GitHub Actions: você envia o projeto
uma vez e baixa o `.exe` pronto. **Passo a passo em [`COMO-GERAR-O-EXE.md`](COMO-GERAR-O-EXE.md).**

Se preferir compilar na sua própria máquina, veja **“Gerar o executável”** mais abaixo.

### Sobre o ffmpeg

O ClipForge usa o **ffmpeg** para cortar os vídeos. A Forma A traz um ffmpeg automaticamente (via
`imageio-ffmpeg`); a Forma B embute ffmpeg+ffprobe no executável. Se preferir, instale o ffmpeg do sistema
([ffmpeg.org/download.html](https://ffmpeg.org/download.html)) — o app usa o que encontrar. Se faltar, ele avisa
numa janela ao abrir.

### Token e privacidade

O app roda só no **seu** computador (`localhost`), e a janela já entra autenticada. O **token da API** (que a
extensão usa) é criado automaticamente em `data/api_token.txt` e aparece no painel pelo botão 🔑.

> A primeira transcrição **baixa o modelo do Whisper** (algumas centenas de MB) — precisa de internet nessa
> primeira vez; depois roda offline.

> A primeira transcrição **baixa o modelo do Whisper** (algumas centenas de MB) — precisa de internet nessa
> primeira vez. Depois roda offline. Em CPU, prefira o modelo `small`; com placa NVIDIA, use `whisper_device:
> cuda` e `whisper_compute: float16` nas Configurações.

## 2. Instalar a extensão do Chrome

1. Abra `chrome://extensions`, ligue o **Modo do desenvolvedor**.
2. **Carregar sem compactação** → selecione a pasta `extension/`.
3. Clique no ícone ✂ → **Configurações** → confira o endereço (`http://localhost:8765`) e cole o **token**
   (de `data/api_token.txt`). Salve.

Pronto. Abra um vídeo ou live do YouTube: aparece o botão **“✂ Cortar com ClipForge”** abaixo do título. Ou
use o popup da extensão para colar vários links, ou o botão direito → **“Cortar com ClipForge”**.

## 3. Conectar YouTube e TikTok (opcional, para publicar)

Sem conectar nada, o app já gera e guarda os cortes para você baixar. Para **publicar automático**, preencha as
chaves no arquivo `.env` (copie de `.env.example`) e conecte as contas na aba **Contas**.

Como o login OAuth exige uma URL de retorno **HTTPS acessível pela internet**, rode um túnel apontando para a
porta 8765 e ponha a URL `https` em `PUBLIC_BASE_URL`:

```bash
# exemplo com cloudflared (gratuito)
cloudflared tunnel --url http://localhost:8765
# copie a URL https:// gerada para PUBLIC_BASE_URL no .env e reinicie o app
```

- **YouTube:** no [Google Cloud Console](https://console.cloud.google.com), crie um projeto, ative a
  **YouTube Data API v3**, gere um **ID do cliente OAuth** (tipo *Aplicativo da Web*) e cadastre a URL de
  redirecionamento que aparece na aba **Contas** (algo como `https://SEU-TUNEL/auth/youtube/callback`). Cole
  `client_id` e `client_secret` no `.env`.
- **TikTok:** em [developers.tiktok.com](https://developers.tiktok.com), crie um app, adicione **Login Kit** e
  **Content Posting API**, ative **Direct Post**, cadastre a URL de redirecionamento (`.../auth/tiktok/callback`,
  HTTPS) e cole `client_key`/`client_secret` no `.env`.

Depois, na aba **Contas**, clique em **Conectar** para cada uma e conclua o login.

---

## Como usar no dia a dia

1. Mande links pela extensão (vídeos gravados **ou** lives).
2. Acompanhe na aba **Fontes**: baixando → transcrevendo → escolhendo trechos → renderizando.
3. Veja os cortes na aba **Cortes**: cada um tem miniatura, player, nota (quão “viral” o trecho é), título
   editável e o selo *Parte N*. Se `auto_approve` estiver ligado, já entram na fila; senão, você **Aprova** os
   que quiser.
4. Em **Fila**, veja o calendário de publicação. Cada plataforma publica **1 corte por horário**, nos
   horários definidos, todo dia, em ordem: Parte 1, Parte 2, Parte 3…
5. **Configurações** controla tudo: horários, plataformas, duração dos cortes, nota mínima, estilo das
   legendas, idioma, atraso das lives, etc.

### Lives ao vivo (quase em tempo real)

Ao mandar o link de uma **live**, o app começa a **gravar em segmentos** e vai cortando conforme a transmissão
avança. O ajuste-chave é o **“Atraso antes de cortar” (`live_delay_seconds`, padrão 180 s)**: o decisor só
corta trechos que já **terminaram** há pelo menos esse tempo. Isso garante que o assunto se fechou antes de
decidir o ponto de corte — você não perde contexto no meio de uma fala. Ao encerrar a live (ou clicar em
**Encerrar live**), o que sobrou é cortado na hora, sem atraso.

### Como ele escolhe os “melhores” trechos

A transcrição (com tempo por palavra) vira frases; janelas de frases viram candidatos. Cada candidato recebe
uma nota por sinais que costumam prender atenção: **gancho** no início (pergunta, número, palavras como
“segredo”, “erro”, “ninguém”…), **ritmo** da fala, **pouco silêncio**, **ênfase/energia** do áudio e um
**fechamento** de ideia. O corte sempre começa e termina em frase completa. Opcionalmente, uma **IA local
gratuita (Ollama)** reavalia os melhores candidatos e sugere um título — ligue em Configurações se tiver o
[Ollama](https://ollama.com) rodando (`ollama_enabled`). Sem ela, as regras já selecionam e titulam sozinhas.

As legendas são estilo “karaokê” (a palavra falada acende em destaque), queimadas no vídeo, com o selo da
parte. Dá para trocar fonte, tamanho, cores e maiúsculas nas Configurações.

---

## Perguntas comuns

**Preciso da API paga do Claude?** Não. A seleção de cortes usa regras locais e, se quiser, o Ollama (grátis,
offline). Nada neste projeto depende de API paga de IA.

**O computador precisa ficar ligado?** Sim, para processar e para publicar nos horários. Se desligar, ao
reabrir o app ele retoma: vídeos voltam para a fila e posts atrasados saem aos poucos. (Lives interrompidas por
desligar o PC não são retomadas automaticamente.)

**Os vídeos saíram privados no YouTube / só aparecem para mim no TikTok.** É a regra de projeto/app sem
auditoria descrita lá em cima — não é bug. Peça a auditoria de cada plataforma para publicar público.

---

## Gerar o executável (Forma B)

### Na nuvem (recomendado, sem instalar nada) — GitHub Actions

O fluxo em `.github/workflows/build.yml` compila **Windows, macOS e Linux** automaticamente e você baixa os
executáveis prontos. Guia completo com telas: [`COMO-GERAR-O-EXE.md`](COMO-GERAR-O-EXE.md).

### Na sua máquina

Rode **no mesmo sistema operacional** do destino (não dá para gerar o .exe do Windows a partir do Mac/Linux).
Defina `CLIPFORGE_ONEFILE=1` para sair um arquivo único; sem isso, sai a pasta `dist/ClipForge` (abre mais rápido).

- **Windows:** duplo clique em `packaging\build_windows.bat` → `dist\ClipForge\ClipForge.exe`.
- **macOS:** duplo clique em `packaging/build_mac.command` → `dist/ClipForge/ClipForge`
  (opcional: `./packaging/make_mac_app.sh` cria um `ClipForge.app`).
- **Linux:** `./packaging/build_linux.sh` → `dist/ClipForge/ClipForge`.

Os scripts instalam o PyInstaller, **baixam ffmpeg+ffprobe** (via `packaging/fetch_ffmpeg.py`) e empacotam tudo.

## Desenvolvimento e testes

```bash
cd backend
python -m pytest -q            # tudo (os testes de vídeo real são lentos: ~15 min)
python -m pytest -q tests/test_highlights.py tests/test_scheduler.py tests/test_captions_publishers.py tests/test_api.py   # rápidos
```

Os testes rodam **sem internet**: usam um vídeo sintético (ffmpeg) e um transcritor falso, então cobrem o
pipeline de cortes, o modo live (com atraso e cortes incrementais), as legendas, os publicadores (YouTube e
TikTok, com as chamadas de rede simuladas) e o agendador.

### Estrutura

```
clipforge/
├─ Iniciar-ClipForge.bat / .command   # abrir o app com um clique (Forma A)
├─ run.py                      # iniciar via terminal (modo servidor)
├─ requirements.txt
├─ .env.example                # chaves do YouTube/TikTok
├─ backend/
│  └─ app/
│     ├─ desktop.py            # lançador: janela nativa + servidor embutido (ponto de entrada do app)
│     ├─ main.py               # API FastAPI + serve o painel
│     ├─ config.py  db.py      # configurações e SQLite
│     ├─ jobs.py               # fila (VOD em série, cada live em sua thread)
│     ├─ scheduler.py          # fila diária de publicação (Parte N)
│     ├─ media.py              # resolve e chama ffmpeg/ffprobe
│     ├─ pipeline/             # download, transcribe, highlights, captions, render, process, live
│     ├─ publishers/           # youtube.py, tiktok.py
│     └─ static/               # painel web (HTML/CSS/JS)
├─ packaging/                  # PyInstaller: spec, build por SO, download do ffmpeg
└─ extension/                  # extensão do Chrome (Manifest V3)
```

## Limitações conhecidas

- Instagram Reels não entra nesta versão (combinado: começar por Shorts + TikTok).
- A nota de “viral” é uma heurística calibrada em dados sintéticos; ajuste `min_score` com vídeos reais.
- A publicação depende das auditorias e cotas de cada plataforma, descritas acima.
