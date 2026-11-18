# Subir o ClipForge no seu GitHub e gerar o ClipForge.exe (pelo terminal)

Faça isto **uma vez**, no seu Windows. Ao final, o GitHub compila o `ClipForge.exe` sozinho e você baixa pronto.

> Antes de começar: descompacte o `clipforge.zip` numa pasta (ex.: `C:\Users\SEU_USUARIO\clipforge`).
> Todos os comandos abaixo são rodados **de dentro dessa pasta**.

---

## Passo 0 — Instalar Git e GitHub CLI (só na primeira vez)

Abra o **PowerShell** (tecla Windows → digite "PowerShell" → Enter) e rode:

```powershell
winget install --id Git.Git -e --source winget
winget install --id GitHub.cli -e --source winget
```

Depois **feche e abra o PowerShell de novo** (para ele reconhecer os programas).

> Não tem o `winget`? Instale manualmente: Git em https://git-scm.com/download/win e o GitHub CLI em
> https://cli.github.com/ . O resto é igual.

---

## Passo 1 — Entrar na pasta do projeto

Troque o caminho pelo lugar onde você descompactou:

```powershell
cd "$env:USERPROFILE\clipforge"
```

Confirme que está na pasta certa (deve listar `README.md`, `backend`, `extension`, `packaging`…):

```powershell
dir
```

---

## Passo 2 — Logar na sua conta do GitHub

```powershell
gh auth login
```

Responda assim quando perguntar:
- **What account?** → `GitHub.com`
- **Preferred protocol?** → `HTTPS`
- **Authenticate Git with your GitHub credentials?** → `Y` (sim)
- **How to authenticate?** → `Login with a web browser`

Ele mostra um **código** (ex.: `AB12-CD34`) e abre o navegador. Cole o código, clique em **Authorize**. Pronto.

---

## Passo 3 — Enviar o projeto e criar o repositório (um comando faz tudo)

```powershell
git init
git add .
git commit -m "ClipForge: app de cortes automaticos (backend + painel + extensao + empacotamento)"
gh repo create clipforge --private --source=. --remote=origin --push
```

O último comando **cria** o repositório `clipforge` na sua conta e **envia** tudo. A compilação começa sozinha.

> Se aparecer um aviso perguntando o nome do branch, pode ignorar. Se o `git commit` reclamar de identidade,
> rode uma vez:
> ```powershell
> git config --global user.name "Seu Nome"
> git config --global user.email "seu@email.com"
> ```
> e repita o `git commit` e o `gh repo create`.

---

## Passo 4 — Acompanhar e baixar o ClipForge.exe

Ver a compilação pelo terminal (fica atualizando até terminar):

```powershell
gh run watch
```

Quando terminar (verde), baixe o executável do Windows direto para uma pasta `ClipForge`:

```powershell
gh run download --name ClipForge-Windows --dir ClipForge
```

Vai aparecer `ClipForge\ClipForge.exe`. **Duplo clique nele** e usar.
(Na 1ª vez o Windows mostra um aviso azul do *SmartScreen* → **Mais informações → Executar assim mesmo**.)

> Prefere pelo site? Abra `https://github.com/devredflag/clipforge` → aba **Actions** → clique na execução
> verde → seção **Artifacts** → baixe **ClipForge-Windows** (vem num .zip; dentro está o `ClipForge.exe`).

---

## Se mudar algo depois

Toda vez que quiser gerar uma nova versão do `.exe` com suas alterações:

```powershell
git add .
git commit -m "ajustes"
git push
```

O push dispara uma nova compilação automaticamente.

---

## Alternativa sem o GitHub CLI (só Git)

1. Crie o repositório vazio no site: https://github.com/new → nome `clipforge` → **Private** → **sem** marcar
   "Initialize" → **Create repository**.
2. No PowerShell, dentro da pasta do projeto:

```powershell
git init
git add .
git commit -m "ClipForge"
git branch -M main
git remote add origin https://github.com/devredflag/clipforge.git
git push -u origin main
```

Na primeira vez o Git pede login do GitHub numa janela — faça o login. Depois é só acompanhar pela aba
**Actions** do repositório e baixar o artefato **ClipForge-Windows**, como no Passo 4.
