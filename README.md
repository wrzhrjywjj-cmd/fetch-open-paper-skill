# Fetch Open Paper

一个面向 Codex 的论文检索与下载 Skill。输入论文标题、完整引文、DOI、PMID 或 arXiv ID 后，它会寻找合法公开版本，下载 PDF，核对题名与作者，并把结果整理到当前任务的 `outputs` 文件夹中。

## 主要功能

- 支持单篇或批量输入：论文名、引文、DOI、PMID、arXiv ID。
- 从出版社开放页面、PubMed Central、Europe PMC、arXiv、HAL、SSRN、Zenodo、高校仓储和作者主页等公开来源寻找候选版本。
- 接受正式出版版、接受稿、作者稿、仓储副本和预印本；不因缺少正式版而直接判定失败。
- 直接请求遇到 HTML 页面、JavaScript 跳转或 HTTP 401/403 时，可转入普通浏览器继续查找公开下载入口。
- 下载后解析 PDF，并根据规范题名和作者姓氏验证论文身份。
- 只把通过验证的文件保存到目标目录；无法可靠验证的文件标记为需要人工核验。
- 批量任务维护可恢复的 `下载结果.csv`，记录候选链接、尝试次数、版本类型、来源和结果。
- 使用论文规范题名命名 PDF；Windows 文件名中的禁用字符和控制字符统一替换为 `_`。

## 安装

### 让 Codex 安装

在 Codex 中输入：

```text
请从 https://github.com/wrzhrjywjj-cmd/fetch-open-paper-skill 安装 fetch-open-paper skill
```

### 手动安装

1. 下载或克隆本仓库。
2. 将仓库内容放到：

   ```text
   C:\Users\<你的用户名>\.codex\skills\fetch-open-paper\
   ```

3. 确认 `SKILL.md` 位于上述目录的根部，而不是额外嵌套一层仓库文件夹。
4. 重新启动 Codex，或重新加载技能列表。

验证脚本需要 Python 3 和 `pypdf`：

```powershell
python -m pip install pypdf
```

如果普通 `python` 不可用，Codex 可以改用工作区内置的 Python 运行时。浏览器回退需要可用的 Chrome 控制能力，但不影响直接公开 PDF 的下载。

## 使用方法

安装后，直接把论文信息交给 Codex 即可。例如：

```text
10.1001/jama.289.18.2387
```

```text
Lunney JR, Lynn J, Foley DJ, Lipson S, Guralnik JM. Patterns of functional decline at the end of life. JAMA. 2003;289:2387-2392.
```

```text
请依次下载下面这些论文 PDF：
1. <论文标题或 DOI>
2. <论文标题或 DOI>
3. <论文标题或 DOI>
```

当当前任务尚未确定输出目录时，Skill 只在第一次询问文件夹名称；确定后，后续论文继续使用同一个目录，除非用户明确要求更换。

## 输出结构

假设第一次指定的文件夹名称为 `JPSMpaper`：

```text
outputs/
└── JPSMpaper/
    ├── Patterns of functional decline at the end of life.pdf
    ├── 另一篇论文题目.pdf
    └── 下载结果.csv
```

文件名中的以下字符会被替换为 `_`：

```text
< > : " / \ | ? *
```

## 下载与验证流程

1. 解析并补全论文的规范题名、作者和 DOI。
2. 按 DOI 优先、题名次之进行批量去重。
3. 建立多个公开候选来源，不在第一个链接失败后停止。
4. 优先尝试直接下载；遇到网页跳转或访问限制时，继续使用普通浏览器检查公开入口。
5. 检查 PDF 文件头、文件大小和可解析性。
6. 对照 PDF 元数据及前五页文本，验证题名相似度和至少一位作者姓氏。
7. 验证通过后才写入目标目录，并更新 `下载结果.csv`。

题名相似度默认阈值为 `0.80`，单个下载文件的安全上限为 `100 MB`。扫描版若缺少可提取文字，只有在 PDF 元数据能够可靠确认题名和作者时才会自动通过，否则标记为 `需人工核验`。

## 任务状态

`下载结果.csv` 使用以下状态：

| 状态 | 含义 |
| --- | --- |
| `待处理` | 已加入任务，尚未开始 |
| `直接下载中` | 正在尝试直接 PDF 地址 |
| `需浏览器尝试` | 直接请求得到网页、跳转或访问限制，需要普通浏览器继续 |
| `浏览器下载中` | 正在浏览器中获取公开文件 |
| `已验证下载` | PDF 已下载，题名与作者验证通过 |
| `需人工核验` | PDF 可获得，但机器无法可靠确认身份 |
| `未完成下载` | 已穷尽当前合法公开候选，仍未完成 |

成功结果按以下格式报告：

```text
论文名称 — 已验证下载
```

未完成的论文会返回论文名称及当前最佳公开下载页或落地页链接。

## 脚本命令

通常由 Skill 自动调用；也可以手动使用。

下载并验证直接 PDF：

```powershell
python .\scripts\download_pdf.py `
  --url "<公开 PDF 地址>" `
  --title "<规范论文题名>" `
  --author "<作者姓氏>" `
  --output-dir ".\outputs\<文件夹名称>"
```

验证浏览器下载的本地 PDF：

```powershell
python .\scripts\download_pdf.py `
  --file "<本地 PDF 路径>" `
  --title "<规范论文题名>" `
  --author "<作者姓氏>" `
  --output-dir ".\outputs\<文件夹名称>"
```

同一篇论文可多次传入 `--author`。脚本只有在验证成功后才会复制、重命名并保存文件。

## 合规边界

本 Skill 只查找和下载合法公开的论文版本。它不会绕过验证码、登录、订阅、许可确认或付费墙，也不会使用 Sci-Hub、影子图书馆、泄漏副本或来源不明的转载站点。普通登录确有必要时，会请用户自行登录后再继续。

## 仓库结构

```text
fetch-open-paper-skill/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
└── scripts/
    ├── download_pdf.py
    └── update_manifest.py
```

