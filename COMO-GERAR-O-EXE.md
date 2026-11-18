# Como obter o ClipForge.exe pronto (sem instalar nada no seu PC)

O GitHub compila o executável para você **na nuvem**. Você só envia o projeto uma vez e baixa o
`ClipForge.exe` pronto. Depois, é só duplo clique — ele faz tudo sozinho: sobe o servidor, resolve o ffmpeg e
abre a janela do app. Não precisa de Python nem de nenhum passo manual.

## Passo a passo (uma vez)

1. **Crie uma conta no GitHub** (grátis): https://github.com/join
2. **Crie um repositório**: botão **+** (canto superior direito) → **New repository** → dê um nome
   (ex.: `clipforge`) → **Create repository**.
3. **Envie os arquivos do projeto** para esse repositório. Jeito mais fácil, sem comandos:
   - Na página do repositório, clique em **uploading an existing file** (ou **Add file → Upload files**).
   - Arraste **todo o conteúdo da pasta `clipforge`** (inclusive a pasta oculta `.github`) para a página.
     - Dica: se o seu Windows não mostra a pasta `.github`, ative *Itens ocultos* no Explorador de Arquivos
       (menu **Exibir → Mostrar → Itens ocultos**).
   - Clique em **Commit changes**.
4. **A compilação começa sozinha.** Abra a aba **Actions** do repositório. Vai aparecer um fluxo chamado
   **“Gerar executável ClipForge”** rodando (bolinha amarela). Espere ficar verde (uns 5–10 minutos).
   - Se preferir disparar na mão: **Actions** → selecione o fluxo → **Run workflow**.
5. **Baixe o executável.** Clique na execução que terminou (verde) → desça até **Artifacts** → clique em
   **`ClipForge-Windows`**. Vai baixar um `.zip`; dentro dele está o **`ClipForge.exe`**.
6. **Use.** Extraia o `ClipForge.exe` para onde quiser (ex.: Área de Trabalho) e dê **duplo clique**. Na primeira
   abertura o Windows pode mostrar um aviso azul do *Windows Defender SmartScreen* (porque o app não tem
   assinatura paga) — clique em **Mais informações → Executar assim mesmo**.

Pronto. A partir daí é só clicar no `ClipForge.exe` sempre que quiser usar.

## Quer um link de download fixo?

Se você criar uma **tag de versão**, o GitHub monta uma **Release** com os três executáveis (Windows, Mac,
Linux) anexados, com link direto para baixar. Pela interface: aba **Releases** → **Draft a new release** →
em *Choose a tag* digite `v0.1.0` → **Publish release**. O fluxo roda e anexa os arquivos à Release.

## Observações

- O primeiro **corte** de vídeo baixa o modelo de transcrição (algumas centenas de MB) — precisa de internet
  nessa primeira vez; depois funciona offline.
- O `.exe` gerado é grande (~800 MB) porque traz a IA de transcrição e o ffmpeg embutidos. É normal.
- O arquivo único demora alguns segundos a mais para abrir na primeira vez de cada sessão (ele se extrai numa
  pasta temporária). Se preferir abertura instantânea, dá para gerar a versão em pasta (veja o `README.md`).
