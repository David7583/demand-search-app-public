# Demand Search App

[简体中文](README.md) | **English**

A Windows browser-based local application for discussing needs, developing plans, reviewing requirement versions and continuing searches on official shopping sites. Current scope: single-user desktop use. Mobile, WeChat device work and public hosting are paused.

This is an independent [public experimental source copy](https://github.com/David7583/demand-search-app-public); the original private repository is retained. Application-original code, scripts and tests use **AGPL-3.0-only**; original documentation and synthetic catalog data use **CC BY 4.0**. Third-party materials retain their licenses. Source publication is not hosted deployment or production-security certification. See [License scope](LICENSE-STATUS.md) and [Validation](docs/VALIDATION.md).

## Start and configure

For an initialized checkout, double-click **Start-Demand-Assistant.cmd** to open [http://127.0.0.1:8000](http://127.0.0.1:8000). **Stop-Demand-Assistant.cmd** stops the background service. Closing a tab does not stop it or delete saved history.

Fresh setup requires Windows x86_64, CPython **3.12.7**, Node.js **24.18.0** and npm **11.16.0**. Run from the project root:

```powershell
./scripts/init.ps1 -Python python
npm.cmd --prefix apps/client run build:h5
./scripts/start-local.ps1
```

Python dependencies live in this project's .venv; frontend dependencies have their own node_modules. Neither uses the NCP environment. An existing Python of the required version can create the isolated environment. See [Environment](docs/ENVIRONMENT.md) and [Local desktop guide](docs/LOCAL-DESKTOP.md).

Use the initial AI wizard or open Settings later. Providers include OpenAI, DeepSeek, Kimi, Qwen and custom OpenAI-compatible endpoints. Select a provider, enter a key, discover models or supply a model ID, consent to the external test, then test and save. A failed test preserves the previous valid configuration.

**Enter keys only in the local configuration page, never in chat or Git.** Windows current-user DPAPI protects stored keys. Conversation text and history remain local SQLite data; protect your account, backups and exports.

## Workflow

1. Describe a wish or task in **AI Chat** without completing every field first. Enable continuous AI understanding and review the data scope and API costs to process subsequent messages automatically; otherwise messages can remain local records.
2. The assistant proposes a plan, offers exploratory directions or organizes an actionable result. Critical risks require verification. Streamed responses become drafts only after full validation.
3. Use **Solution Workspace** to review options, assumptions, estimates, steps, evidence and versions. Desktop supports page switching, a wide-screen side-by-side view and a collapsible sidebar.
4. Use the revision action on an earlier reply to reference that version. References persist with messages. A revision creates a new version without automatically rolling back or overwriting confirmed requirements.
5. Confirm requirements and adopt a plan separately. Estimates are not quotes; assumptions are not facts; confirming a need is not a purchase commitment.
6. Generate search links from a confirmed list and inspect keywords before opening a site. Lists support up to 30 items and conversations can be resumed. Preserve unsent text before refreshing.

Switch the interface between **中文 / English** independently of the shopping market. Changing interface language does not translate or rewrite user text, existing AI replies, search terms or NCP data, and does not call a model. You can converse in your preferred language.

## Shopping destinations

| Market | Official search destinations |
|---|---|
| China | Taobao, JD.com, Pinduoduo |
| United States | Amazon US, eBay US, Walmart US |
| International | Etsy |

These are official keyword-search URLs, **not product API connections**. The application does not retrieve products, prices or inventory, compare products across platforms automatically, or place orders. Market selection does not translate terms, convert currencies or verify delivery. Sites may require login, JavaScript or human verification; access varies by network and region. See [Provider status](docs/PROVIDER-STATUS.md) and [Commerce alternatives](docs/PRODUCT-SOURCES.md).

## Simulated market

Open **Simulated market** in the top navigation to browse by keyword or category without an AI key. The reusable catalog contains **500 fictional merchants, 50 categories and 1,500 synthetic products or services**, spanning daily needs, travel, AI devices, software, professional services and industrial equipment. Merchant details expose their NCP capability declarations.

You can also ask the AI how many fictional merchants and offerings are available, or which categories are covered. It receives an actual local catalog summary with bilingual category names. This is catalog awareness, not product retrieval or verified supply. On a fresh installation, open Simulated market once to initialize its database.

In **Solution Workspace**, select a confirmed requirement version and choose **Search simulated market**. Candidates are grouped by list item, with matching reasons, budget status and unresolved conditions. Sending candidate feedback to chat prepares an unsent revision request; it does not confirm requirements, order anything or invoke AI.

All merchant, price, qualification, stock and delivery information is synthetic. It is **not a live product source or evidence of independent merchant adoption**. A separate persistent SQLite database survives restarts and stores no user conversations or queries. The repository includes reproducible catalog source, initialization tools and a separately generated [sanitized synthetic database snapshot](data/simulated-market/README.md); daily-use databases and configuration remain excluded. See [Simulated market guide](docs/SIMULATED-MARKET.md).

## NCP and MCP

Related protocol: [NeedConcord Protocol (NCP)](https://github.com/David7583/needconcord-protocol). Application and protocol code, Git history, environments and data are independent. The public name NCP remains distinct from the wire identifier **`ODIP/0.1.3-exp.1`**.

The app validates and exports a private local subset: intent.publish, intent.update and intent.withdraw. Detailed lists use an application-specific namespace. The simulated market additionally generates and validates capability.advertise and proposal.submit, linking proposals to the selected confirmed intent. This is local simulation within one implementation, not NCP node transport, real merchant exchanges or cross-implementation interoperability. See [Compatibility](docs/NCP-COMPATIBILITY.md).

**MCP has been investigated but is not implemented.** A future optional server can reuse the application through a small adapter. MCP does not grant commerce access or guarantee better understanding. See [NCP/MCP assessment](docs/research/NCP-MCP-ASSESSMENT.md).

## Validation and limitations

```powershell
./.venv/Scripts/python.exe scripts/verify.py --stage S5 --target desktop --browser
./.venv/Scripts/python.exe scripts/smoke_launcher.py
```

Automation uses isolated synthetic data and model providers, not real credentials or private conversations. Test builds go to .local/s2-client, separate from daily-use assets. Read [Validation](docs/VALIDATION.md) for actual results and failures. A workflow file alone does not prove a successful remote CI run.

Prior desktop repairs recorded zero findings in full and production npm audits; new audits are reported separately. Original 55 findings/seven critical and intermediate 14 findings remain local historical evidence, not current unresolved findings. Zero advisories do not prove production security. See [Security status](docs/SECURITY-BLOCKERS.md).

The minimal snapshot excludes the original PRD, development history, internal audits, real configurations, databases, logs, caches and backups. The service is loopback-only; changing its bind address is not safe public deployment. Production security, multi-user isolation, WeChat devices and NCP cross-implementation interoperability remain unverified.

Initiator and initial maintainer: **David7583**. Development is AI-assisted; third-party rights and attribution are retained, without claiming exclusive ownership of all material. Application code uses AGPL-3.0-only and original documentation uses CC BY 4.0. Imported NCP assets retain their original Apache-2.0/CC BY 4.0 terms. See [License status](LICENSE-STATUS.md), [Security](SECURITY.md) and [Release boundaries](docs/RELEASE-CHECKLIST.md).
