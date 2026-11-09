# Synthetic market database

This directory contains one deliberately publishable **synthetic** SQLite artifact:
`market.synthetic.sqlite3`. It was generated from the fixed source seed in a fresh,
isolated SQLite store, then written through a temporary export directory.
It was **not copied from any runtime database**.

- Seed date: `2026-11-09`; seed and store versions: `1`.
- Exactly 50 categories, 500 fictional merchants, and 1,500 synthetic offerings.
- Only `market_metadata` and `merchants` tables, plus their primary-key indexes.
- Merchant names, zones, capabilities, specifications, prices and lead times are fictional.
- No conversations, user queries, demand versions, proposals tied to users, credentials,
  tokens, real organizations, contact details or transaction records are included.
- All merchant/offer/price records explicitly declare `data_origin: synthetic`.
- File SHA-256: `253dba7aa3cc2bc8ff2e7feaf2aa96ff18ba24bb4e8dfca276e72b76240e2602`.
- Canonical catalog-and-capabilities SHA-256:
  `1c2b594f910c25e25c508bbf7df25d13977c2e85b33a754593695ea6da63c5e2`.

## Generate or verify

From the project root, using its pinned Python environment:

```powershell
.venv\Scripts\python.exe scripts\export_simulated_market.py
.venv\Scripts\python.exe scripts\export_simulated_market.py --verify
```

The exporter has one fixed destination and an exclusive export lock. An identical,
fully validated existing artifact is reused. Different bytes are rejected, never silently
overwritten. The exporter never reads or changes `runtime/demand-search.sqlite3` or
`runtime/simulated-market.sqlite3`. Binary reproducibility is deliberately tied to the
pinned SQLite/Python build; a changed binary needs review. Existing snapshots are validated
independently of the current serializer; a new export that differs from the reviewed hash is refused.

The secret scanner's exception is restricted to this exact path. It validates the supplied
Git-index or archive bytes in a query-only in-memory connection with trusted_schema disabled,
checks the exact two-table schema and complete source-derived catalog, and requires equality
with the fixed reviewed file SHA-256 above. This also excludes deleted-cell remnants, unused
pages, extra tables and appended data. Verification of the existing snapshot does not regenerate
SQLite bytes, so serializer differences between Python/SQLite builds do not reject an intact file. Every other SQLite path remains rejected.

## Local use without overwriting

The application does not automatically import this checked-in artifact. Prefer regenerating
the independent runtime market from the same source:

```powershell
.venv\Scripts\python.exe scripts\init_simulated_market.py
```

That command creates a missing runtime market or verifies an existing one; it never silently
resets an existing database. Do not copy this artifact over an existing runtime store.
If a manual import is required, first verify the artifact and use exclusive destination
creation only when `runtime/simulated-market.sqlite3` does not exist. Never use the main
`runtime/demand-search.sqlite3` path. Explicit `--rebuild` on the initialization command is
a separate user-chosen replacement operation for the synthetic market only.

这是可入库的纯合成演示数据库，包含500家虚构商家、1500项模拟商品/服务。
生成过程不读取真实运行库，不包含用户查询、密钥或任何真实商家资料；与真实组织无关联。
重新导出仅复用完全相同的文件；不同文件会拒绝覆盖。运行库初始化和手动导入均不得覆盖现有数据。

## License / 许可

The designated synthetic catalog data and database rights, where held by the project, use CC BY 4.0. The generator code uses AGPL-3.0-only. Attribute Demand Search App / David7583 and retain third-party notices. See [license scope](../../LICENSE-STATUS.md). All data remains fictional.

合成目录数据采用CC BY 4.0，生成器代码采用AGPL-3.0-only；仅涉及项目有权许可的部分，不改变第三方权利。
