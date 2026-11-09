# Selected NeedConcord Protocol assets

This directory contains **only the assets needed for the Demand Search App S2 local adapter**. It does not contain the upstream implementation, environment, original archive or Git history.

- Public project: [NeedConcord Protocol](https://github.com/David7583/needconcord-protocol).
- Wire identifier: `ODIP/0.1.3-exp.1`.
- Fixed public documentation/source reference: `88def78378c9c95f80976f3c11a261019236486d`, recorded during the S0 source review.
- Import source: read-only local upstream commit `cff62700a63a9ae599d73fdd7ed5245a921326cc`, verified clean before copying.
- Exact source paths, SHA-256 values and import decisions: [ncp-import-lock.json](../../config/ncp-import-lock.json).
- Original S0 observations remain in local development records, excluded from the minimal private snapshot. The import lock above documents the actual selected assets.

All 21 imported files retain their exact original bytes. Schema and machine-readable synthetic vectors are licensed under Apache-2.0 within the upstream licensor's rights. Copied original documentation is CC BY 4.0 within those rights. Full applicable texts, the original NOTICE, license scope and provenance record are retained. No exclusive ownership of AI-assisted or uncertain historical material is asserted. Application-authored code and documentation retain the application's separate AGPL-3.0-only / CC BY 4.0 license scope.

Some original notice/document links point to files not copied in this minimal selection. Read those targets in the [fixed upstream snapshot](https://github.com/David7583/needconcord-protocol/tree/88def78378c9c95f80976f3c11a261019236486d); they are not runtime dependencies.

## Tests and boundaries

[Selected cases](selected-cases.json) is an application-created subset index preserving each upstream ID, rule and expectation. Fifteen selected vectors run **Schema assertions only**. It is not the full upstream manifest or a claim of 42/42 or 53/53 conformance.

In particular, `private-network-intent` is structurally valid but forbidden by upstream **network** semantics. A local private representation is allowed here. This app does not send that data to another NCP node, does not run the upstream network expectation, and does not report it as a passed network test.

The adapter is written independently from the specification and imported Schema. It validates only the app's local private `intent.publish`, `intent.update` and `intent.withdraw` lifecycle. It generates no receipt or delivery claim. Independent code plus selected fixture results does **not** establish cross-implementation transport interoperability.
